// Fixture: secret logged (seeded) + a redacted log (control).

export function onLogin(token: string): void {
  // SEEDED BUG [LOG-1]: full bearer token written to the log.
  console.log(`auth ok, token=${token}`);
}

export function onLoginSafe(token: string): void {
  // CLEAN CONTROL: only a redacted prefix is logged.
  console.log(`auth ok, token=${token.slice(0, 4)}…`);
}
