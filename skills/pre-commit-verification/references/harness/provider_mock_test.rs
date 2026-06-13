// Smoke test [8]: external APIs — fixture-based provider tests (R2.11.1).
//
// External providers (OAuth, mail APIs, calendar APIs, webhooks) fail in ways
// your unit tests never see because unit tests mock the provider away entirely.
// This pins the provider CONTRACT against a local mock server (wiremock): the
// real client code runs, hits the mock, and we assert the request it sends and
// the way it handles the response (including error responses). Provider drift,
// wrong auth header, bad request shape, and unhandled error codes get caught
// locally instead of in production.
//
// Uses `wiremock` (add to dev-dependencies). Place in tests/ and name so it's
// discoverable. One representative test per provider interaction you depend on.
//
// CUSTOMIZE: the client under test, the endpoint paths, the request assertions,
// and the response fixtures.

use wiremock::matchers::{header, method, path};
use wiremock::{Mock, MockServer, ResponseTemplate};

// CUSTOMIZE: import the real client/service under test from your crate.
// use backend::services::mail::MailClient;

#[tokio::test]
async fn provider_token_refresh_sends_correct_request_and_handles_200() {
    let server = MockServer::start().await;

    // CUSTOMIZE: the provider's token endpoint and the success fixture.
    Mock::given(method("POST"))
        .and(path("/oauth/token"))
        .and(header("content-type", "application/x-www-form-urlencoded"))
        .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
            "access_token": "fixture-access",
            "refresh_token": "fixture-refresh",
            "expires_in": 3600
        })))
        .expect(1) // assert the client calls it exactly once
        .mount(&server)
        .await;

    // CUSTOMIZE: point the real client at the mock base URL and run the path.
    // let client = MailClient::with_base_url(server.uri());
    // let tokens = client.refresh_token("old-refresh").await.expect("refresh ok");
    // assert_eq!(tokens.access_token, "fixture-access");

    // .expect(1) above is verified on drop; if the client didn't send the
    // request (wrong URL, skipped path) this test fails.
    let _ = &server;
}

#[tokio::test]
async fn provider_handles_401_without_panicking() {
    let server = MockServer::start().await;

    // CUSTOMIZE: a realistic error fixture for an expired/invalid token.
    Mock::given(method("GET"))
        .and(path("/v1/messages"))
        .respond_with(ResponseTemplate::new(401).set_body_json(serde_json::json!({
            "error": "invalid_grant"
        })))
        .mount(&server)
        .await;

    // CUSTOMIZE: assert the client surfaces a typed error, not a panic/unwrap.
    // let client = MailClient::with_base_url(server.uri());
    // let err = client.list_messages().await.expect_err("should error on 401");
    // assert!(matches!(err, MailError::AuthExpired));
    let _ = &server;
}

// CUSTOMIZE: add one test per external interaction you actually depend on —
// rate-limit (429) handling, malformed-body handling, pagination, webhook
// signature verification, etc. The goal is to pin the contract you rely on so
// provider-side drift is caught here rather than in production.
