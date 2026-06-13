# Extraction by Language

Language-specific notes for extracting imports, exports, and function signatures from source files. Most languages can be handled with the same general approach (read the file, identify import statements and function definitions), but each has edge cases worth knowing.

Default extraction strategy: read the file, identify language by extension, apply the patterns below. Use Claude's reading comprehension — don't rely on regex alone for anything non-trivial.

---

## TypeScript / JavaScript

**Imports to extract:**

```typescript
import foo from './foo';                          // default: kind=default, symbols=[]
import { a, b } from './bar';                     // named: kind=named, symbols=[a,b]
import { a as x } from './bar';                   // named with rename: symbols=[a] (track 'a', not 'x')
import * as ns from './baz';                      // namespace: kind=namespace, symbols=[]
import './side-effect';                            // side_effect: kind=side_effect, symbols=[]
const m = await import('./dynamic');              // dynamic: kind=dynamic, symbols=[]
import type { T } from './types';                 // named with type-only — still track, mark as type-only
```

**Exports to record (file-level):**

- `export default X`
- `export { a, b }`
- `export const x = ...`, `export function f() {}`, `export class C {}`
- `export * from './re-export'` — track as re-export

**Function signatures:**

- Function declarations: `function foo(a: A, b: B): R { ... }` → signature `(a: A, b: B) => R`
- Arrow functions assigned to const: `const foo = (a: A): R => ...` → signature `(a: A) => R`
- Methods on classes: include class name in qualified name (`MyClass.method`)
- Anonymous functions inside other functions: only record if they're significant (e.g., named, or exported as callbacks)

**Call extraction:** identify function-call expressions in the body. Don't try to resolve method dispatch perfectly — record `obj.method` as written. Resolution happens when consumers query the codemap.

**JSX:** components used in JSX (`<Foo />`) count as calls to `Foo`. Useful for finding component usage.

**Edge cases:**

- Re-exports (`export { foo } from './bar'`) create both an import edge from this file to `./bar` and an export at this file. Track both.
- Path aliases (`@/components/Foo` resolving via tsconfig paths): resolve them when possible by reading `tsconfig.json`'s `paths` field. If unresolvable, record the alias as-written and note in warnings.
- `require()` calls in CommonJS: treat as imports of kind `default` if assigned, `side_effect` if not.

---

## Rust

**Imports to extract:**

```rust
use std::collections::HashMap;            // path: 'std::collections', symbols: ['HashMap']
use crate::auth::refresh;                 // path: 'crate::auth', symbols: ['refresh']
use super::store::{Save, Load};           // path: 'super::store', symbols: ['Save', 'Load']
use crate::db::*;                         // path: 'crate::db', kind: 'namespace'
```

`crate::` paths resolve to files within the same crate. Use the crate's module structure (Cargo.toml + directory layout + `mod` declarations) to map module paths to file paths.

**Function signatures:**

- Free functions: `fn foo(a: A, b: B) -> R { ... }` → signature `(a: A, b: B) -> R`
- Methods: `impl Foo { fn bar(&self, x: X) -> Y { ... } }` → qualified name `Foo::bar`, signature `(&self, x: X) -> Y`
- Async: prefix with `async fn` in signature
- Generic functions: include type parameters in signature

**Call extraction:**

- Function calls: `foo(x, y)`, `Bar::method(x)`, `self.foo()`
- Macro invocations: include common macros that imply call-like behavior (`println!`, `vec!`, `dbg!`, `assert!`)

**Edge cases:**

- `mod foo;` declarations create a module that resolves to either `foo.rs` or `foo/mod.rs` — treat as importing everything from that module
- `pub use` re-exports: track as both import and re-export
- Cargo workspace members: cross-crate imports resolve to files in sibling crates
- Procedural macros and `build.rs` are entry points (covered in entry-point-patterns.md)

---

## Python

**Imports to extract:**

```python
import os                                  # path: 'os', kind: 'namespace'
import os.path as path                     # path: 'os.path', kind: 'namespace'
from typing import List, Dict              # path: 'typing', symbols: ['List', 'Dict']
from .helpers import format_date           # path: 'helpers' (relative), symbols: ['format_date']
from ..utils import logger                 # path: '../utils', symbols: ['logger']
from . import constants                    # path: '.', symbols: ['constants']
import importlib                           # dynamic via importlib — note but don't try to resolve
```

Resolve relative imports against the file's package structure (`__init__.py` files define packages). Standard library imports (`os`, `sys`, etc.) are external dependencies.

**Function signatures:**

- `def foo(a: int, b: str = "x") -> bool: ...` → signature `(a: int, b: str = 'x') -> bool`
- `async def foo(...)` → signature prefixed with `async`
- Methods: include class in qualified name
- Lambdas: usually skip unless assigned to a name

**Decorators:**

- Record decorators applied to functions (they often indicate concerns: `@cached`, `@async_to_sync`, `@deprecated`, `@app.route('/x')`)
- A function with `@app.route` decorator is likely an API endpoint — tag `api`

**Edge cases:**

- `__init__.py` files: their imports often re-export for the package; track as imports and exports
- Dynamic imports via `importlib.import_module(name)`: note in extraction but don't try to resolve
- Type checking imports inside `if TYPE_CHECKING:` blocks: still track, mark as type-only
- Star imports (`from x import *`): track but flag as concerning in warnings (makes refactoring hard)

---

## Go

**Imports:** in `import` blocks. Group by standard / third-party / internal based on path. Internal imports (within the module) resolve to package directories — use `go.mod` to find the module root.

**Function signatures:** `func Foo(a A, b B) (R, error) { ... }` → signature `(a A, b B) -> (R, error)`. Methods: `func (r *Receiver) Foo(...) ...` → qualified name `Receiver.Foo`.

**Exports:** Go uses capitalization for visibility. `Foo` is exported, `foo` is not. Record `exported: true` based on first-letter capitalization.

---

## Java / Kotlin

**Imports:** `import com.example.Foo;` (Java) or `import com.example.Foo` (Kotlin). Wildcard imports (`import com.example.*`) treat as namespace.

**Function signatures:** include access modifiers, return type, parameter types. Kotlin's expression-body functions count.

**Methods on classes:** qualified name is `ClassName.methodName`.

---

## Ruby

**Imports:** `require 'foo'`, `require_relative './bar'`. Note that Ruby's `require` is dynamic at runtime; resolving the file path may need fallbacks.

**Function signatures:** `def foo(a, b = 'x'); ...; end` → signature `(a, b = 'x')`. Methods inside classes/modules: qualified name `Class#method` for instance methods, `Class.method` for class methods.

---

## Markdown / Documentation (v0.2.1)

Markdown (`.md`, `.mdx`), reStructuredText (`.rst`), and plain text (`.txt`) files are documentation, not code. Cartographer v0.2.1 includes them in `structure.json` with `kind: "documentation"`.

**Triage at build time.** Each documentation file is classified into one of three classes based on filename, location, content patterns, and (if present) `.codemap/spec-config.yml`:

- **`spec`** — design specs, plans, roadmaps, architecture docs. The high-information class.
- **`operational`** — conventions, contributing guides, style guides.
- **`informational`** — README, CHANGELOG, user guides, miscellaneous.

See `SKILL.md` "Documentation files (v0.2.1 addition)" for full triage rules.

**Section structure.** For each documentation file, count top-level section markers (`## `, `### \d+`, `§\d+`) and record as `section_count`. Do NOT extract section-level data as records in v0.2.1 — that's deferred to v0.3 documentation.json. Just the count, for audit's awareness.

**Spec_refs extraction from explicit annotations.** Even in non-spec documentation, scan for explicit `@spec:` markers in code blocks (e.g., a README may mention `// @spec: v3 §8.1` in an example). Treat these the same as if they appeared in source code.

**Cross-references between docs.** Track only when a doc explicitly references another with a markdown link `[other doc](./OTHER.md)`. Don't try to resolve fuzzy "see also" mentions.

**External dependencies.** Documentation files don't have external dependencies in the package-manager sense. Leave `external_dependencies` empty.

**Function extraction.** Documentation files have no functions. Don't populate `functions.json` entries for them.

**Dependencies graph.** Documentation files get an entry in `dependencies.json` with empty `imports_from` and `external_dependencies`. Their `imported_by` may be populated if other docs link to them (via markdown link extraction above) — useful for finding orphan docs.

**Spec-class docs get special treatment:**

1. Build a section-list at extraction time: array of `{ ref, title, loc_range }` from the doc's headers. Used internally for spec_refs inference on source files. Not exposed in structure.json itself in v0.2.1.
2. Mark with `is_canonical_spec: true` if matched as canonical (see SKILL.md).
3. Record `spec_version` (e.g., `"v3"`) extracted from the filename, title, or explicit `version:` markers.

---

## SQL

SQL files are a special case — they don't have "functions" in the same sense, but they have:

- Schema objects (tables, views, indexes, types) — list these as "functions" with `kind: schema_object`
- Stored procedures / functions — list as functions with their parameters
- Cross-references via FK constraints — these are dependencies between tables, useful for `dependencies.json`

For migration files, record the migration as a single entity with `tags: ['migration-file', 'db']` and don't try to extract sub-functions.

---

## HTML / CSS

Generally not tracked at function level. For `structure.json`:

- HTML: record as `kind: source` with appropriate tags (`ui`, `entry-point` if it's a build target)
- CSS: record as `kind: source` with tag `ui`. Imports (`@import url(...)`) become dependencies.

Don't populate `functions.json` for HTML/CSS files.

---

## Mixed / unknown languages

If a file's extension isn't recognized:

- Try to identify language from shebang line or content
- If identifiable, apply best-fit extraction
- If not, record in `structure.json` as `kind: other` with no language, leave `functions.json` empty for it
- Note in the Cartographer run summary: "N files of unknown language not extracted"

---

## General principles for all languages

**Be conservative.** When in doubt about an import or call, record it as best you can rather than guessing. A consumer querying the codemap can deal with "this import resolved to multiple possible paths" but not with "this import is missing entirely."

**Don't over-extract.** Skip private helpers that are clearly internal (`_helper`, leading underscore, `private fn`) when listing functions, unless they're called from outside their defining scope. The point is to map the meaningful surface, not every line.

**Match the language's idioms.** Signature format should look like the language: TypeScript arrow notation, Rust `->`, Python `->`. Don't normalize to a single artificial format.

**Spec refs.** Look for these comment patterns across all languages:
- `// @spec: v3 §X.Y` or `# @spec: v3 §X.Y`
- `/** @spec v3 §X.Y */`
- `// implements: v3 §X.Y`

Extract whatever comes after the marker, normalize to "v3 §X.Y" form.
