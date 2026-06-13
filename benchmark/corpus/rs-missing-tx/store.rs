// Fixture: two writes without a transaction (seeded) + a transactional one (control).

use rusqlite::Connection;

// SEEDED BUG [TX-1]: debit and credit are separate writes; a crash between
// them leaves money missing. No transaction wraps the pair.
pub fn transfer(conn: &Connection, from: i64, to: i64, cents: i64) -> rusqlite::Result<()> {
    conn.execute("UPDATE acct SET bal = bal - ?1 WHERE id = ?2", (cents, from))?;
    conn.execute("UPDATE acct SET bal = bal + ?1 WHERE id = ?2", (cents, to))?;
    Ok(())
}

// CLEAN CONTROL: the same pair wrapped in a transaction — must NOT be flagged.
pub fn transfer_safe(conn: &mut Connection, from: i64, to: i64, cents: i64) -> rusqlite::Result<()> {
    let tx = conn.transaction()?;
    tx.execute("UPDATE acct SET bal = bal - ?1 WHERE id = ?2", (cents, from))?;
    tx.execute("UPDATE acct SET bal = bal + ?1 WHERE id = ?2", (cents, to))?;
    tx.commit()
}
