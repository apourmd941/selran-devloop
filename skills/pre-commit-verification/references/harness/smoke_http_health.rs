// Smoke test [1+4]: runtime + build-graph.
//
// Launches the actual built binary, waits for it to come up, fetches the health
// endpoint WITH an Origin header (so the cross-origin/CORS path is exercised the
// way the webview hits it), and asserts:
//   - HTTP 200
//   - a CORS allow-origin header is present and echoes/permits the webview origin
//   - the process emitted at least one non-empty startup log line
//
// This is the test that catches "binary built but won't boot", "health route
// 500s under a real request", "CORS layer missing/misconfigured at runtime", and
// "starts silently with no logging". Unit tests on the handler pass in isolation;
// only a launched process proves these.
//
// Place in tests/smoke/ and name so `cargo test --test 'smoke_*'` picks it up.

use std::io::{BufRead, BufReader};
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};

// CUSTOMIZE: how the built binary is launched and on what address.
const BINARY_ENV: &str = "SMOKE_BINARY"; // path to built binary; falls back below
const DEFAULT_BINARY: &str = "target/debug/backend"; // CUSTOMIZE
const HEALTH_URL: &str = "http://127.0.0.1:8765/api/health"; // CUSTOMIZE
const WEBVIEW_ORIGIN: &str = "tauri://localhost"; // CUSTOMIZE: the origin the webview sends
const BOOT_TIMEOUT: Duration = Duration::from_secs(15);

#[test]
fn health_responds_200_with_cors_and_logs() {
    let binary = std::env::var(BINARY_ENV).unwrap_or_else(|_| DEFAULT_BINARY.to_string());

    let mut child = Command::new(&binary)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap_or_else(|e| panic!("failed to launch binary at {binary}: {e}"));

    // Capture startup logs on a background thread so we can assert non-empty output.
    let stdout = child.stdout.take().expect("child stdout");
    let log_handle = std::thread::spawn(move || {
        let mut first_nonempty = String::new();
        for line in BufReader::new(stdout).lines().flatten() {
            if !line.trim().is_empty() {
                first_nonempty = line;
                break;
            }
        }
        first_nonempty
    });

    // Poll the health endpoint until it answers or we time out.
    let deadline = Instant::now() + BOOT_TIMEOUT;
    let mut last_err = String::from("never attempted");
    let mut response: Option<HealthProbe> = None;
    while Instant::now() < deadline {
        match probe_health(HEALTH_URL, WEBVIEW_ORIGIN) {
            Ok(p) => {
                response = Some(p);
                break;
            }
            Err(e) => {
                last_err = e;
                std::thread::sleep(Duration::from_millis(300));
            }
        }
    }

    // Always tear the process down before asserting, so a failure doesn't leak it.
    let _ = child.kill();
    let _ = child.wait();
    let first_log = log_handle.join().unwrap_or_default();

    let probe = response.unwrap_or_else(|| {
        panic!("health endpoint never responded within {BOOT_TIMEOUT:?}: {last_err}")
    });

    assert_eq!(probe.status, 200, "health endpoint returned {}", probe.status);
    assert!(
        probe.cors_allow_origin.is_some(),
        "no Access-Control-Allow-Origin header on health response — CORS layer missing at runtime"
    );
    let allow = probe.cors_allow_origin.unwrap();
    assert!(
        allow == "*" || allow == WEBVIEW_ORIGIN,
        "CORS allow-origin '{allow}' does not permit webview origin '{WEBVIEW_ORIGIN}'"
    );
    assert!(
        !first_log.trim().is_empty(),
        "binary produced no startup log line — silent boot"
    );
}

struct HealthProbe {
    status: u16,
    cors_allow_origin: Option<String>,
}

// CUSTOMIZE: replace this hand-rolled probe with the repo's HTTP client of choice
// (reqwest, ureq, etc.) if one is already a dev-dependency. Kept dependency-free
// here so the template compiles without adding crates.
fn probe_health(url: &str, origin: &str) -> Result<HealthProbe, String> {
    use std::io::Write;
    use std::net::TcpStream;

    let stripped = url.strip_prefix("http://").ok_or("only http:// supported in template")?;
    let (host_port, path) = match stripped.split_once('/') {
        Some((hp, p)) => (hp, format!("/{p}")),
        None => (stripped, "/".to_string()),
    };

    let mut stream = TcpStream::connect(host_port).map_err(|e| format!("connect: {e}"))?;
    stream
        .set_read_timeout(Some(Duration::from_secs(3)))
        .map_err(|e| e.to_string())?;
    let req = format!(
        "GET {path} HTTP/1.1\r\nHost: {host}\r\nOrigin: {origin}\r\nConnection: close\r\n\r\n",
        host = host_port.split(':').next().unwrap_or(host_port)
    );
    stream.write_all(req.as_bytes()).map_err(|e| format!("write: {e}"))?;

    let mut raw = String::new();
    BufReader::new(&mut stream)
        .read_line(&mut raw)
        .map_err(|e| format!("read status: {e}"))?;
    let status = raw
        .split_whitespace()
        .nth(1)
        .and_then(|c| c.parse::<u16>().ok())
        .ok_or_else(|| format!("unparseable status line: {raw:?}"))?;

    let mut cors = None;
    let reader = BufReader::new(&mut stream);
    for line in reader.lines().flatten() {
        if line.is_empty() {
            break; // end of headers
        }
        if let Some((k, v)) = line.split_once(':') {
            if k.trim().eq_ignore_ascii_case("access-control-allow-origin") {
                cors = Some(v.trim().to_string());
            }
        }
    }

    Ok(HealthProbe { status, cors_allow_origin: cors })
}
