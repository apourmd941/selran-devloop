// Fixture: permissive CORS on an API router (seeded) + explicit control.
// Mirrors a real shakedown finding (2026-06-12, confirmed High).
use axum::Router;
use tower_http::cors::CorsLayer;

pub fn router_bad(api: Router) -> Router {
    // SEEDED BUG [ACORS-1]: any website's JS can read this API from the browser.
    api.layer(CorsLayer::permissive())
}

pub fn router_safe(api: Router) -> Router {
    // CLEAN CONTROL: explicit origin — must NOT be flagged.
    let cors = CorsLayer::new()
        .allow_origin("http://localhost:12096".parse::<axum::http::HeaderValue>().unwrap());
    api.layer(cors)
}
