#!/usr/bin/env python3
"""Every create-skill ast-grep recipe finds the exports it is meant to find.

ast-grep's JSON output never reports the kind of the node a rule matched, so
create-skill copies a matched export's `ast_node_type` from the `kind` its
recipe declares (#530). This test:

  - parses every recipe (a ```yaml block holding a mapping with `id`,
    `language` and `rule`) in src/skf-create-skill/references/**/*.md, and
    the inline `find_code_by_rule` example, and checks that each `rule`
    names its kind and captures the export's name as `$NAME`;
  - checks that src/shared/data/ast-grep-recipes.yaml, the recipe file
    skf-extract-public-api.py --mode full runs, holds the same rules as
    extraction-patterns.md (#584), with metadata the prose agrees with: the
    languages the language notes run each recipe in, and the recipe sets
    (component-extraction.md names its recipes by id and holds no copy);
  - with the ast-grep version package.json's `test:python` pins on PATH
    (`uv run --with ast-grep-cli==0.45.3`), runs each recipe over fixtures
    holding the forms it must find and the forms it must skip (taken from
    the pass that designed the recipes and then tried to break them), also
    under each other language extraction-patterns.md's language notes run it
    with (`language:` rewritten), checks the exact (file, $NAME's line, NAME)
    matches, that each Python / TS / JS line is a definition line by the
    provenance verifier's rules, that the verifier's kind-at gives the
    recipe's kind at each line, and that the recipe finds nothing once its
    declared kind is swapped for a neighbouring one. Every run has matches
    to find. It also runs the CLI streaming template's Python over a recipe's
    output, and the recipe runner over the fixtures, whose exports must be
    exactly the (file, first line, name, kind) the recipes' matches give.
    With no ast-grep binary, or another version, those runs are skipped.
"""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
REFS = REPO / "src" / "skf-create-skill" / "references"
PATTERNS = REFS / "extraction-patterns.md"
COMPONENT_EXTRACTION = REFS / "component-extraction.md"
DATA_FILE = REPO / "src" / "shared" / "data" / "ast-grep-recipes.yaml"
RUNNER = REPO / "src" / "shared" / "scripts" / "skf-extract-public-api.py"


def _pinned_version() -> str:
    """The ast-grep-cli version package.json's test:python installs."""
    scripts = json.loads((REPO / "package.json").read_text(encoding="utf-8"))["scripts"]
    match = re.search(r"--with ast-grep-cli==([\w.]+)", scripts["test:python"])
    assert match, "package.json test:python pins no ast-grep-cli version"
    return match.group(1)


PINNED_VERSION = _pinned_version()

FENCE_RE = re.compile(r"^```yaml\n(.*?)^```", re.M | re.S)
# The inline example is a JSON string: `\n` a line break, `\"` a quote, `\\` a backslash.
INLINE_RULE_RE = re.compile(r'^\s*yaml="(id: (?:[^"\\]|\\.)*)",?$', re.M)
CLI_TEMPLATE_RE = re.compile(
    r'^ast-grep scan -r \{recipe_file\} --json=stream \{path\} \| python3 -c "\n(.*?)^" \| head -\{HEAD_CAP\}$',
    re.M | re.S,
)

# id -> the kind of the node the recipe matches, verified on ast-grep 0.45.3
KINDS = {
    "python-public-functions": "function_definition",
    "python-public-classes": "class_definition",
    "js-exported-functions": "export_statement",
    "js-exported-constants": "export_statement",
    "js-exported-arrow-functions": "export_statement",
    "js-exported-classes": "export_statement",
    "ts-exported-types": "export_statement",
    "js-reexports": "export_specifier",
    "js-namespace-reexports": "export_statement",
    "js-local-exports": "export_specifier",
    "rust-public-functions": "function_item",
    "go-exported-functions": "function_declaration",
    "react-props-interfaces": "export_statement",
    "react-component-functions": "export_statement",
    "react-component-arrow-functions": "export_statement",
    "react-wrapped-components": "export_statement",
    "vue-define-props": "call_expression",
    "vue-define-props-tsx": "call_expression",
}

# (id, language of its block) -> the other languages the language notes run
# it with, by rewriting `language:`: tsx for .tsx files, typescript for .ts,
# javascript for .js / .jsx.
VARIANTS = {
    ("js-exported-functions", "typescript"): ("tsx",),
    ("js-exported-constants", "typescript"): ("tsx", "javascript"),
    ("js-exported-arrow-functions", "typescript"): ("tsx", "javascript"),
    ("js-exported-classes", "typescript"): ("tsx", "javascript"),
    ("ts-exported-types", "typescript"): ("tsx",),
    ("js-reexports", "typescript"): ("tsx", "javascript"),
    ("js-namespace-reexports", "typescript"): ("tsx", "javascript"),
    ("js-local-exports", "typescript"): ("tsx", "javascript"),
    ("react-props-interfaces", "typescript"): ("tsx",),
    ("react-component-functions", "tsx"): ("typescript",),
    ("react-component-arrow-functions", "typescript"): ("tsx", "javascript"),
    ("react-wrapped-components", "tsx"): ("typescript", "javascript"),
}

# The Vue recipes run in both recipe sets: the AST Extraction Protocol runs
# them on .vue files at any scope, and they are component-library recipes.
VUE_RECIPES = {"vue-define-props", "vue-define-props-tsx"}
EXPORT_TYPES = {"function", "class", "const", "interface", "type", "enum", "re-export"}

# A kind next to each declared one (the declaration inside an export, the
# statement around a call, a bodyless fn): swapped in, it matches nothing.
NEIGHBOUR_KINDS = {
    "function_definition": "decorated_definition",
    "class_definition": "decorated_definition",
    "export_statement": "lexical_declaration",
    "export_specifier": "export_clause",
    "function_item": "function_signature_item",
    "function_declaration": "method_declaration",
    "call_expression": "expression_statement",
}

# --------------------------------------------------------------------------
# Fixtures: the line numbers below are the ones EXPECTED cites. ast-grep reads
# a .vue file only with an sgconfig.yml that maps it to HTML (SGCONFIG, written
# beside the rule file, outside the fixtures, as extraction-patterns.md's Vue
# note says); its <script lang="ts"> blocks then go to the typescript recipes
# and <script lang="tsx"> to the tsx ones.
# --------------------------------------------------------------------------

FIXTURES = {
    "api.py": """\
__all__ = ["search", "fetch", "Client", "Missing"]

def search(query: str, top_k: int = 10) -> list:
    def inner_helper(x):
        return x
    class InnerClass:
        pass
    return []

def _private(x):
    return x

async def fetch(url):
    return url

@functools.cache
@functools.wraps(search)
def cached(key):
    return key

@dataclass
class Client:
    def update(self, value):
        if value:
            def branch_local(): pass
        return value

    @staticmethod
    async def aclose():
        return None

    class Nested:
        pass

class _Hidden:
    pass

class Derived(Client):
    pass

if HAS_FAST:
    def fast_path(): pass
else:
    class FallbackPath: pass
try:
    def try_def(): pass
except ImportError:
    def _except_private(): pass
finally:
    class FinallyClass: pass
with suppress(Exception):
    def with_def(): pass
for _k in range(1):
    def loop_def(): pass
while False:
    def while_def(): pass
    class WhileClass: pass
""",
    "edge.py": '''\
"""def in_docstring(): pass
class InDocstring: pass"""
# def commented(): pass
SRC = "class InString:\\n    def in_string(self): pass"
def generic[T](x: T) -> T:
    return x
async def agen[T: (int, str)](x: T): pass
@overload
def ov[*Ts, **P](x: int) -> int: ...
class Box[T](Generic[T], metaclass=Meta):
    def meth[U](self, u: U) -> U: return u
def \\
    spaced (  # ) : def fake():
    a, /, *, c=lambda: (1), **kw
) -> "def g(): pass": ...
@register(lambda: None)
async def decorated_async(): pass
def ñame(): return 1
class Ünï: x = 1
def _(): pass
class _Priv: pass
def outer():
    global made_global
    def made_global(): pass
    @dataclass
    class InFunc: pass
    if True:
        class InIfInFunc: pass
try:
    class Guarded:
        with ctx():
            def in_with_in_class(self): pass
        if X:
            @staticmethod
            def in_if_in_class(): pass
except ImportError:
    pass
if TYPE_CHECKING:
    class Proto: pass
match MODE:
    case "fast":
        def fast_impl(): pass
if __name__ == "__main__":
    def main_only(): pass
    class MainOnly: pass
else:
    def imported_branch(): pass
if ('__main__' == __name__):
    @cli.command
    def main_rev(): pass
if __name__ != "__main__":
    class NotMain: pass
''',
    "functions.ts": """\
// positives
export function plain(a: string) {
  return a;
}
export function typed(a: string): number {
  return 1;
}
export async function asyncFn(url: string): Promise<string> {
  return url;
}
export function* gen(): Generator<number> {
  yield 1;
}
export async function* agen() {
  yield 1;
}
export function pair<A, B>(a: A, b: B) {
  return [a, b];
}
export function identity<T extends object>(x: T): T {
  return x;
}
export default function Main() {}

// overloads: each signature matches, the implementation does not
export function over(a: string): string;
export function over(a: number): number;
/** implementation: its signature is hidden from callers */
export function over(a: any): any {
  return a;
}

export declare function ambient(x: number): void;

// negatives
function internal() {}
async function internalAsync() {}
export const arrow = (a: string) => a;
export const expr = function named() {};
export const api = { get() {} };
export class Store {
  method() {}
  static create() {}
}
export interface Api {
  fetch(): void;
}
export namespace NS {
  export function inner() {}
}
export { internal };
""",
    "anon.ts": """\
// negative: an anonymous default export has no name to capture
export default function () {}
""",
    "tricky.ts": """\
// export function inComment() {}
/* export function inBlock() {} */
const s = "export function inString() {}";
const t = `
export function inTemplate() {}
`;
export
function
split
<T>
(
  x: T,
): T { return x; }
export /* c */ async /* d */ function /* e */ spaced() {}
export function isStr(x: unknown): x is string { return typeof x === "string"; }
export function assertStr(x: unknown): asserts x is string {}
export function withConst<const T extends readonly unknown[]>(x: T): T { return x; }
export function usesUsing() {
  using res = open();
  return res satisfies object;
}
export function type() {}
export function declare() {}
export function async() {}
export function $dollar() {}
export function outer() {
  function nestedInner() {}
  return function nestedExpr() {};
}
export function ov(a: string): string
export function ov(a: number): number // trailing comment
// line comment between
export function ov(a: any): any { return a; }
export function nextAfterImpl() {}
export declare function amb(): void
export declare namespace AmbNS { function notTop(): void; }
declare module "pkg" {
  export function augment(): void;
}
declare global {
  function globalFn(): void;
}
@sealed
export class Decorated {}
export function afterDecorated() {}
function localSig(a: string): void;
function localSig(a: any) {}
export { localSig as aliased };
export const arrowish = async <T,>(x: T) => x;
""",
    "ambient.d.ts": """\
declare module "pkg" {
  export function pkgFn(a: string): void;
  export function pkgFn(a: number): void;
  namespace Deep { export function deepFn(): void; }
}
declare module Legacy { export function legacyFn(): void; }
declare namespace NSx { export function nsFn(): void; }
export namespace Real { export function realFn(): void; }
declare global { export function globFn(): void; }
""",
    "components.tsx": """\
// positives
export function Card(props: CardProps) {
  return <div>{props.title}</div>;
}

export function Typed({ title }: CardProps): JSX.Element {
  return <h1>{title}</h1>;
}

export async function ServerList(): Promise<JSX.Element> {
  return <ul />;
}

export function List<T,>(props: { items: T[] }) {
  return <ul>{props.items.length}</ul>;
}

export function Select<T extends string>(props: { value: T }): JSX.Element {
  return <select value={props.value} />;
}

export default function App() {
  return <Card title="x" />;
}

// overloads: each signature matches, the implementation does not
export function Poly(props: { as: "a" }): JSX.Element;
export function Poly(props: { as: "b" }): JSX.Element;
export function Poly(props: any) {
  return null;
}

// negatives
export function useCard() {
  return null;
}
export function formatTitle(t: string): string {
  return t;
}
function Hidden() {
  return <span />;
}
export const Panel = (props: CardProps) => <section />;
export const Memo = function Inner() {
  return <i />;
};
export class Legacy extends React.Component {
  Render() {
    return null;
  }
}
export interface CardProps {
  title: string;
}
""",
    "tricky.tsx": """\
// export function CommentComp() {}
const label = "export function StringComp() {}";
export function Generic<T>(props: { v: T }) {
  return <p>export function JsxText() {"{}"} {/* export function JsxComment() {} */}</p>;
}
export default
function DefaultSplit() { return <div />; }
export function GET(req: Request) { return new Response(); }
export function URLBar() { return <nav />; }
export function _Private() { return null; }
export function Outer() {
  function InnerComp() { return <b />; }
  return <InnerComp />;
}
export const Wrapped = memo(function Named() { return <i />; });
export function Over(p: { a: 1 }): JSX.Element
export function Over(p: { a: 2 }): JSX.Element
/** docs */
// more
export function Over(p: any) { return <u />; }
export function AfterOver() { return <s />; }
export declare function DeclaredComp(p: {}): JSX.Element;
export namespace UI {
  export function NsComp() { return <hr />; }
}
@observer
export class Store {}
export function AfterDecorator() { return <em />; }
export function lower() { return <i />; }
export async function* StreamComp() { yield <li />; }
export function Ünicode() { return <i />; }
export function
  Multi
  <P extends object,>
  (props: P)
  : JSX.Element { return <>{"x"}</>; }
export { Outer as Renamed };
""",
    "gen.tsx": """\
export function* SagaRoot() { yield 1; }
export async function* StreamRows() { yield <tr />; }
export default function* DefaultGen() { yield null; }
export function Real() { return <div />; }
""",
    "memo.tsx": """\
export default memo(function MemoDefault() { return <i />; });
""",
    "plain.js": """\
export function jsA() {}
export default async function JsDefault() {}
export function* jsGen() {}
function hidden() {}
export { hidden };
export const arrow = () => {};
""",
    "comp.jsx": """\
export function JsxCard() { return <div />; }
export default function JsxApp() { return <JsxCard />; }
export function useThing() {}
export function Élan() { return <i />; }
""",
    "decls.ts": """\
export const LIMIT = 10;
export const typedConst: number = 5;
export const first = 1, second = 2;
export const { x, y } = point;
export let counter = 0;
export var legacy = 1;
const local = 1;
export declare const ambient: number;
export const handler = (req, res) => {
  return res;
};
export const typedArrow = (a: number): number => a;
export const asyncArrow = async (url: string): Promise<string> => url;
export const genericArrow = <T>(v: T): T => v;
export const annotated: Handler = () => undefined;
export const single = v => v;
export const Button = (props: ButtonProps) => null;
export const AsyncPanel = async () => null;
export const Wrapped = memo(() => null);
export const fnExpr = function () {};
export let letArrow = () => 1;
const privateArrow = () => 1;
export class Store {}
export class Box<T> {
  value?: T;
}
export class Child extends Store implements Api {}
export abstract class Base<T> extends Box<T> {}
@sealed
export class Decorated {}
export @sealed class Inner {}
export default class DefaultCls {}
export declare class AmbientCls {}
class Hidden {}
export interface ButtonProps {
  label: string;
}
export interface IconProps extends ButtonProps, Aria {
  icon: string;
}
export interface ListProps<T> extends Base<T> {}
export interface Other {}
interface LocalProps {}
export type AliasProps = { a: string };
export { a, b as c } from './x';
export { default as Widget, type WidgetProps } from "./w";
export type { ThemeProps } from './t';
export { default } from './d';
export * as ns from './y';
export * from './z';
export { LIMIT as MAX, Store as Shop };
export const Ünit = () => null;
""",
    "decls.tsx": """\
export const Panel = (props: PanelProps) => <section />;
export const Generic = <T,>(props: ListProps<T>): JSX.Element => <ul />;
export const Typed: FC<CardProps> = ({ title }) => <h1>{title}</h1>;
export const AsyncCard = async () => <div />;
export const helper = (x) => x;
const Local = () => <div />;
export let Mutable = () => <div />;
export const Memo = memo(() => <div />);
export interface CardProps extends Base {
  title: string;
}
export class Widget extends Component<CardProps> {}
export { Card as Tile, type CardProps as TileProps } from './card';
export * as icons from './icons';
""",
    "adv.ts": """\
// export const FakeComment = 1;
/* export class FakeBlock {} */
const tpl = `export const FakeTpl = () => 1; export { fake } from './f'`;
const str = "export interface FakeProps {}";
export
const
  Spread =
  1;
export const/**/Tight = 2;
export const a1 = 1, B2 = () => 2;
export const lower = () => 1, Upper = () => 2;
export const { de } = obj, AfterDestr = 3;
export const Paren = (() => 1);
export const Cast = ((p: P) => null) as FC;
export const Sat = (() => null) satisfies FC;
export const enum Dir { Up }
export namespace NS {
  export const Inner = () => 1;
  export class InnerCls {}
  export interface InnerProps {}
  export { q as r } from './q';
}
namespace Hidden {
  export const HiddenConst = 1;
  export interface HiddenProps {}
}
declare module './aug' {
  export interface AugProps {}
  export class AugCls {}
}
declare global {
  export const G = 1;
}
@Component({
  selector: 'x', template: 'export default',
})
export class Angular {}
export default interface DefaultProps {}
export declare interface DeclaredProps {}
export abstract class Abs {}
export class Over {
  m(): void;
  m(x?: any) {}
}
export default abstract class DefAbs {}
export const Cls = class Named {};
export {
  // comment a as b
  one,
  two as /* c */ three,
  "str-name" as strAlias,
  four as "quoted-out",
} from "./multi";
export * /* c */ as nsC from './c';
export * as "strNs" from './s';
export { im } from './json' with { type: 'json' };
import { X } from './x';
export { X };
function f() { const inFn = 1; }
""",
    "adv.tsx": """\
// export const FakeComment = () => <div/>;
export const Jsx = () => <p>export const FakeJsx = () =&gt; 1</p>;
export const helper = () => 1, Comp = () => <div />;
export const Fwd = forwardRef((p, r) => <div ref={r} />);
export default function Page() { return <main />; }
export const Styled = styled.div`
  export const FakeStyled = 1;
`;
export const Gen = <T extends object>(p: T) => <div />;
export namespace UI {
  export const Inner = () => <div />;
  export interface InnerProps {}
}
@observer
export class ObsStore extends Component<P> {}
export default class DefComp extends Component {}
export { Card as default, type CardProps } from './card';
export { Btn } from './btn';
export interface
  MultiLineProps
  extends A {}
export const Lazy = lazy(() => import('./x'));
""",
    "adv.js": """\
export const A = () => 1;
export const b = 2, C = (x) => x;
export class B extends Base {}
export default class D {}
export { e as f, g } from './e';
export * as h from './h';
@dec export class H {}
export const J = () => <div />;
""",
    "lib.rs": """\
pub fn add(a: i32, b: i32) -> i32 {
    a + b
}
pub fn reset(x: &mut i32) { *x = 0; }
pub async fn fetch(url: &str) -> Result<String, Error> { todo!() }
pub const fn zero() -> u32 { 0 }
pub unsafe fn raw(p: *const u8) -> u8 { *p }
pub extern "C" fn ffi_entry(x: i32) -> i32 { x }
pub const unsafe fn both() {}
/// Docs.
#[inline]
pub fn map<T, U, F>(xs: Vec<T>, f: F) -> Vec<U>
where
    F: Fn(T) -> U,
{
    xs.into_iter().map(f).collect()
}
pub(crate) fn internal() {}
pub(super) fn parent_only() {}
pub(self) fn self_only() {}
pub(in crate::a) fn scoped() {}
fn private() {}

pub struct Point;
pub struct Wrap<T>(T);
impl Point {
    pub fn new() -> Self { Point }
    pub(crate) fn crate_method(&self) {}
    fn hidden(&self) {}
}
impl<T: Clone> Wrap<T> {
    pub async fn get(&self) -> T { self.0.clone() }
}
impl Default for Point {
    fn default() -> Self { Point }
}
pub trait Shape {
    fn area(&self) -> f64;
    fn name(&self) -> &str { "shape" }
}
extern "C" {
    pub fn c_import(x: i32) -> i32;
}
pub mod geo {
    pub fn distance() -> f64 { 0.0 }
    pub(crate) fn helper() {}
    mod inner {
        pub fn hidden_deep() {}
    }
}
pub(crate) mod krate {
    pub fn crate_visible() {}
}
mod private_mod {
    pub fn not_reachable() {}
}
fn outer() {
    pub fn nested() {}
}
""",
    "adv.rs": """\
// pub fn in_comment() {}
/* pub fn in_block_comment() {} */
const S: &str = "pub fn in_string() {}";
pub
fn
split_lines
(
) {}
pub /* c */ fn commented_vis() {}
pub (crate) fn spaced_crate() {}
pub fn r#match() {}
pub fn lifetimes<'a>(s: &'a str) -> &'a str { s }
#[cfg(test)]
pub fn cfg_gated() {}
pub mod a {
    pub mod b {
        pub fn deep_pub() {}
    }
    pub(crate) mod c {
        pub fn under_crate_mod() {}
    }
    impl super::Thing {
        pub fn in_mod_impl() {}
    }
}
mod hidden {
    pub mod exposed_inner {
        pub fn behind_private() {}
    }
    pub struct H;
    impl H {
        pub fn private_mod_method() {}
    }
}
fn host() {
    pub mod local_mod {
        pub fn in_fn_mod() {}
    }
}
const _: () = {
    pub mod anon {
        pub fn in_const_block() {}
    }
};
pub struct Thing;
struct Priv;
impl Priv {
    pub fn private_type_method() {}
}
impl crate::a::Thing2 {
    pub fn scoped_type() {}
}
macro_rules! gen {
    () => { pub fn from_macro() {} };
}
cfg_if::cfg_if! {
    if #[cfg(unix)] { pub fn in_cfg_if() {} }
}
pub trait T { fn req(&self); }
extern "C" { pub fn ext(x: i32); }
""",
    "main.go": """\
package main

func Exported(a int) int {
\treturn a
}

func Unit(a int) {
}

func Pair(a, b string) (int, error) { return 0, nil }

func Named(x int) (n int, err error) { return }

func Variadic(prefix string, args ...any) string { return prefix }

func Map[T, U any](xs []T, f func(T) U) []U { return nil }

func Keys[K comparable, V any](m map[K]V) []K { return nil }

func NoArgs() {}

func Asm(x uint64) uint64

// Doc comment.
func Documented() error { return nil }

func unexported() {}

func init() {}

func main() {}

type T struct{}

func (t T) Method() {}

func (t *T) PtrMethod() int { return 0 }

func (t T) lower() {}

var FuncVar = func() {}

func Outer() {
\tinner := func() {}
\t_ = inner
}
""",
    "adv.go": """\
package adv

import "fmt"

// func Commented() {}
var s = `func InRawString() {}`

func
Split(a int) int { return a }

func Generic[
\tT any,
\tU comparable,
](xs []T, u U) []T {
\treturn xs
}

func Union[T int | float64](xs ...T) T { var z T; return z }

func Constrained[T interface{ ~int }, S ~[]T](s S) {}

func Curried() func(int) func() error { return nil }

func Anon() struct{ X int } { return struct{ X int }{} }

func Chan() <-chan int { return nil }

func Commented /* c */ (a int) {}

func ParamComment(a int /* c */, b int) {}

func Multi(
\ta int,
\tb string,
) (
\tint,
\terror,
) {
\treturn 0, nil
}

func Élan() {}

func _() {}

func (r *Recv[T]) GenericMethod() {}

func (Recv[T]) UnnamedRecv() {}

var Exported = func() {}

func lowerGeneric[T any]() {}

type Recv[T any] struct{}

func Printf() { fmt.Println("func Fake() {}") }

func GenBodyless[T any](x T) T
""",
    "comments.go": """\
package p

func LineComments(
\ta int, // first
\tb string, // second
) error {
\treturn nil
}

func /* c */ AfterFunc() {}

func TP /* c */ [T any]() {}

func TPComment[T any /* c */]() {}

func TPLine[
\tT any, // doc
]() {}

func BeforeResult(a int) /* c */ int { return 0 }

func BeforeBody() int /* c */ { return 0 }

func NoParamsComment(/* none */) {}
""",
    "props.ts": """\
export interface ButtonProps {
  label: string;
}
interface CardProps { title: string }
type Local = { n: number };

const props = defineProps<ButtonProps>();

const withDef = withDefaults(defineProps<CardProps>(), { title: "x" });

defineProps<Local>();

const { label } = defineProps<ButtonProps>();

const inline = defineProps<{ size: number }>();

const qualified = defineProps<Types.PanelProps>();

const generic = defineProps<Wrapper<Inner>>();

const runtime = defineProps({ label: String });

const arr = defineProps(["label"]);

const emits = defineEmits<ButtonEmits>();

const other = useProps<ButtonProps>();
""",
    "props_adv.ts": """\
// defineProps<InComment>()
const s = "defineProps<InString>()";
const t = `defineProps<InTemplate>()`;
const u = `${defineProps<InSubst>()}`;
const spaced = defineProps< Spaced >( );
const multi = defineProps<
  MultiLine
>();
const commented = defineProps</* c */ CommentArg>();
const member = obj.defineProps<MemberCall>();
const optional = defineProps?.<OptionalCall>();
const tq = defineProps<typeof runtimeObj>();
const union = defineProps<A | B>();
const arr = defineProps<Item[]>();
const omit = defineProps<Omit<Props, "x">>();
const two = defineProps<First, Second>();
const withArg = defineProps<WithArg>({});
function setup() {
  const inner = defineProps<InsideFunction>();
}
const nn = defineProps<NonNull>()!;
const asT = defineProps<AsCast>() as unknown;
const parenCallee = (defineProps)<ParenCallee>();
declare function defineProps<T>(): T;
const generic2 = defineProps<Props<T>>();
namespace NS { export const p = defineProps<InNamespace>(); }
const key = defineProps<keyof Foo>();
const lit = defineProps<"literal">();
const intersect = defineProps<A & B>();
const tuple = defineProps<[A]>();
const paren = defineProps<(Parened)>();
""",
    "nest.ts": """\
const arrowExpr = () => defineProps<InArrow>();
class K { f = defineProps<InClassField>(); }
if (flag) { defineProps<InIf>(); }
if (flag) defineProps<UnbracedIf>();
for (;;) defineProps<InFor>();
for (const k of ks) defineProps<InForOf>();
while (x) defineProps<InWhile>();
switch (x) { case 1: defineProps<InCase>(); }
""",
    "Button.vue": """\
<script setup lang="ts">
interface VueButtonProps { label: string }
const props = defineProps<VueButtonProps>();
</script>

<template><button>{{ props.label }}</button></template>
""",
    "A.vue": """\
<script setup lang='ts'>
const p = defineProps<SingleQuoted>();
</script>
""",
    "B.vue": """\
<script lang="ts">
export default { name: "B" };
</script>

<script setup lang="ts">
// defineProps<InTsComment>()
const p = defineProps<SecondBlock>();
</script>
""",
    "C.vue": """\
<script setup lang="tsx">
const p = defineProps<TsxLang>();
</script>
""",
    "D.vue": """\
<!-- defineProps<InHtmlComment>() -->
<script setup lang="ts" generic="T extends string">
const p = defineProps<GenericComp<T>>();
const q = defineProps<PlainInGeneric>();
</script>
<template><div>{{ defineProps<InTemplate>() }}</div></template>
""",
    "F.vue": """\
<script
  setup
  lang="ts"
>
const p = defineProps<MultiLineTag>();
</script>
""",
    "G.vue": """\
<template><p/></template>
<script setup lang="ts">
const p = defineProps<TemplateFirst>();
</script>
<style scoped>
.a { color: red }
</style>
""",
    "H.vue": """\
<script setup lang="TS">
const p = defineProps<UpperLang>();
</script>
""",
    "I.vue": """\
<script setup>
const p = defineProps<JsNoLang>();
</script>
""",
    "J.vue": """\
<script lang="ts" setup>
const p = defineProps<LangFirst>();
</script>
""",
    "K.vue": """\
<script setup lang="tsx">
const inline = defineProps<{ size: number }>();
function render() { return defineProps<InRender>(); }
const qualified = defineProps<Types.TsxProps>();
</script>
""",
    # #559's fixtures: shadcn/ui shapes (a local export list, a wrapped
    # component), wrapped components, and the types component-extraction.md
    # Phase 4 Step 4 extracts (namespace members are not module exports).
    "button.tsx": """\
import * as React from "react"
import { cva } from "class-variance-authority"

const buttonVariants = cva("inline-flex", { variants: {} })

const Button = React.forwardRef<HTMLButtonElement, React.ComponentProps<"button">>(
  (props, ref) => <button ref={ref} {...props} />
)

export { Button, buttonVariants }
""",
    "card.tsx": """\
function Card(props: React.ComponentProps<"div">) {
  return <div {...props} />
}

function CardHeader(props: React.ComponentProps<"div">) {
  return <div {...props} />
}

export { Card, CardHeader }
""",
    "wrapped.tsx": """\
export const Memoed = React.memo(function Memoed() { return <div /> })
export const Forwarded = React.forwardRef<HTMLDivElement, {}>((props, ref) => <div ref={ref} />)
export const Lazy = React.lazy(() => import("./card"))
""",
    "types.ts": """\
export interface Plain { a: string }
export interface Ext extends Plain { b: number }
export interface Gen<T> { value: T }
export type Alias = string | number
export type GenericAlias<T> = { value: T }
export enum Color { Red, Green }
export const enum Flag { On, Off }
export declare enum Declared { A, B }
export namespace NS {
  export interface Inner { x: number }
  export type InnerT = string
  export enum InnerE { X }
}
""",
    "locals.ts": """\
// negatives: a from list, lists inside blocks, an import attribute, no names
export { a } from './a';
declare module "m" {
  export { q };
}
namespace N { const k = 1; export { k }; }
export { im } from './json' with { type: 'json' };
export {};
const x = 1, y = 2, z = 3;
type T = string;
export { x as default };
export type { T };
export { type T as TT, y };
export {
  // comment a as b
  z,
};
export { x as "str-out" };
export { z as zed, };
""",
    "locals.js": """\
const x = 1, y = 2;
export { x as default };
export { y };
export { x as "str-out" };
export { y as why };
""",
    "types_adv.ts": """\
export default interface DefaultI { a: string }
export declare interface DeclI { a: string }
export declare type DeclT = string;
export declare namespace DNS { interface Hidden {} }
declare module "pkg" {
  export interface Aug {}
}
declare global {
  export enum GEnum { A }
}
export type { Plain } from './types';
export interface
  Split
  extends Base {}
export interface Defaults<T = {}> extends Base<T> { v: T }
export type Fn = (a: string) => void;
export type Mapped<K extends string> = { [P in K]: number };
export /* c */ interface Commented {}
interface Local {}
type LocalT = string;
export { Local };
export declare const enum DCE { A }
""",
    "wrapped_adv.tsx": """\
export const A = memo(Inner);
export const B = React.memo<Props>(Inner);
export const C = forwardRef<HTMLDivElement, P>((p, r) => <div ref={r} />);
export const D = lazy(() => import('./d'));
export const lower = memo(Inner);
export let E = memo(Inner);
export const F = observer(Inner);
export const G = React.memo(Inner) as FC;
export const H = (memo)(Inner);
export default memo(function I() { return null; });
export const J = React.lazy(() => import('./j')), k = 1;
export const l = 1, M = memo(Inner);
export const N = styled.div``;
export const O = Foo.memo(Inner);
export namespace NS { export const P = memo(Inner); }
const Q = memo(Inner);
export const R = memo(forwardRef((p, r) => null));
""",
    "wrapped.jsx": """\
export const A = memo(Inner);
export const B = React.forwardRef((p, r) => <div ref={r} />);
export const c = memo(Inner);
""",
    # A Radix primitive's shape (radix-ui/primitives dialog.tsx): its Props
    # interfaces are declared unexported and listed by `export type { ... }`.
    "dialog.tsx": """\
import * as React from "react"

interface DialogProps {
  open?: boolean
}

const Dialog: React.FC<DialogProps> = (props) => null

interface DialogTriggerProps {
  asChild?: boolean
}

const DialogTrigger = React.forwardRef<HTMLButtonElement, DialogTriggerProps>((props, ref) => null)

export { Dialog, DialogTrigger }
export type { DialogProps, DialogTriggerProps }
""",
}

# (id, language) -> sorted (file, 1-based line, captured NAME) the recipe matches
EXPECTED: dict[tuple[str, str], list[tuple[str, int, str]]] = {
    ("python-public-functions", "python"): [
        ("api.py", 3, "search"), ("api.py", 13, "fetch"), ("api.py", 18, "cached"),
        ("api.py", 42, "fast_path"), ("api.py", 46, "try_def"), ("api.py", 52, "with_def"),
        ("api.py", 54, "loop_def"), ("api.py", 56, "while_def"), ("edge.py", 5, "generic"),
        ("edge.py", 7, "agen"), ("edge.py", 9, "ov"), ("edge.py", 13, "spaced"),
        ("edge.py", 17, "decorated_async"), ("edge.py", 18, "ñame"), ("edge.py", 22, "outer"),
        ("edge.py", 42, "fast_impl"), ("edge.py", 47, "imported_branch"),
    ],
    ("python-public-classes", "python"): [
        ("api.py", 22, "Client"), ("api.py", 38, "Derived"), ("api.py", 44, "FallbackPath"),
        ("api.py", 50, "FinallyClass"), ("api.py", 57, "WhileClass"), ("edge.py", 10, "Box"),
        ("edge.py", 19, "Ünï"), ("edge.py", 30, "Guarded"), ("edge.py", 39, "Proto"),
        ("edge.py", 52, "NotMain"),
    ],
    ("js-exported-functions", "typescript"): [
        ("functions.ts", 2, "plain"), ("functions.ts", 5, "typed"), ("functions.ts", 8, "asyncFn"),
        ("functions.ts", 11, "gen"), ("functions.ts", 14, "agen"), ("functions.ts", 17, "pair"),
        ("functions.ts", 20, "identity"), ("functions.ts", 23, "Main"),
        ("functions.ts", 26, "over"), ("functions.ts", 27, "over"), ("functions.ts", 33, "ambient"),
        ("tricky.ts", 14, "spaced"), ("tricky.ts", 15, "isStr"), ("tricky.ts", 16, "assertStr"),
        ("tricky.ts", 17, "withConst"), ("tricky.ts", 18, "usesUsing"), ("tricky.ts", 22, "type"),
        ("tricky.ts", 23, "declare"), ("tricky.ts", 24, "async"), ("tricky.ts", 25, "$dollar"),
        ("tricky.ts", 26, "outer"), ("tricky.ts", 30, "ov"), ("tricky.ts", 31, "ov"),
        ("tricky.ts", 34, "nextAfterImpl"), ("tricky.ts", 35, "amb"),
        ("tricky.ts", 45, "afterDecorated"),
    ],
    ("js-exported-functions", "tsx"): [
        ("adv.tsx", 5, "Page"), ("components.tsx", 2, "Card"), ("components.tsx", 6, "Typed"),
        ("components.tsx", 10, "ServerList"), ("components.tsx", 14, "List"),
        ("components.tsx", 18, "Select"), ("components.tsx", 22, "App"),
        ("components.tsx", 27, "Poly"), ("components.tsx", 28, "Poly"),
        ("components.tsx", 34, "useCard"), ("components.tsx", 37, "formatTitle"),
        ("gen.tsx", 1, "SagaRoot"), ("gen.tsx", 2, "StreamRows"), ("gen.tsx", 3, "DefaultGen"),
        ("gen.tsx", 4, "Real"), ("tricky.tsx", 3, "Generic"), ("tricky.tsx", 7, "DefaultSplit"),
        ("tricky.tsx", 8, "GET"), ("tricky.tsx", 9, "URLBar"), ("tricky.tsx", 10, "_Private"),
        ("tricky.tsx", 11, "Outer"), ("tricky.tsx", 16, "Over"), ("tricky.tsx", 17, "Over"),
        ("tricky.tsx", 21, "AfterOver"), ("tricky.tsx", 22, "DeclaredComp"),
        ("tricky.tsx", 28, "AfterDecorator"), ("tricky.tsx", 29, "lower"),
        ("tricky.tsx", 30, "StreamComp"), ("tricky.tsx", 31, "Ünicode"),
        ("tricky.tsx", 33, "Multi"),
    ],
    ("js-exported-functions", "javascript"): [
        ("comp.jsx", 1, "JsxCard"), ("comp.jsx", 2, "JsxApp"), ("comp.jsx", 3, "useThing"),
        ("comp.jsx", 4, "Élan"), ("plain.js", 1, "jsA"), ("plain.js", 2, "JsDefault"),
        ("plain.js", 3, "jsGen"),
    ],
    ("js-exported-constants", "typescript"): [
        ("adv.ts", 9, "Tight"), ("adv.ts", 10, "a1"), ("adv.ts", 11, "lower"),
        ("adv.ts", 12, "AfterDestr"), ("adv.ts", 13, "Paren"), ("adv.ts", 14, "Cast"),
        ("adv.ts", 15, "Sat"), ("adv.ts", 46, "Cls"), ("decls.ts", 1, "LIMIT"),
        ("decls.ts", 2, "typedConst"), ("decls.ts", 3, "first"), ("decls.ts", 9, "handler"),
        ("decls.ts", 12, "typedArrow"), ("decls.ts", 13, "asyncArrow"),
        ("decls.ts", 14, "genericArrow"), ("decls.ts", 15, "annotated"), ("decls.ts", 16, "single"),
        ("decls.ts", 17, "Button"), ("decls.ts", 18, "AsyncPanel"), ("decls.ts", 19, "Wrapped"),
        ("decls.ts", 20, "fnExpr"), ("decls.ts", 52, "Ünit"), ("functions.ts", 38, "arrow"),
        ("functions.ts", 39, "expr"), ("functions.ts", 40, "api"), ("tricky.ts", 49, "arrowish"),
    ],
    ("js-exported-constants", "tsx"): [
        ("adv.tsx", 2, "Jsx"), ("adv.tsx", 3, "helper"), ("adv.tsx", 4, "Fwd"),
        ("adv.tsx", 6, "Styled"), ("adv.tsx", 9, "Gen"), ("adv.tsx", 22, "Lazy"),
        ("components.tsx", 43, "Panel"), ("components.tsx", 44, "Memo"), ("decls.tsx", 1, "Panel"),
        ("decls.tsx", 2, "Generic"), ("decls.tsx", 3, "Typed"), ("decls.tsx", 4, "AsyncCard"),
        ("decls.tsx", 5, "helper"), ("decls.tsx", 8, "Memo"), ("tricky.tsx", 15, "Wrapped"),
        ("wrapped.tsx", 1, "Memoed"), ("wrapped.tsx", 2, "Forwarded"), ("wrapped.tsx", 3, "Lazy"),
        ("wrapped_adv.tsx", 1, "A"), ("wrapped_adv.tsx", 2, "B"), ("wrapped_adv.tsx", 3, "C"),
        ("wrapped_adv.tsx", 4, "D"), ("wrapped_adv.tsx", 5, "lower"), ("wrapped_adv.tsx", 7, "F"),
        ("wrapped_adv.tsx", 8, "G"), ("wrapped_adv.tsx", 9, "H"), ("wrapped_adv.tsx", 11, "J"),
        ("wrapped_adv.tsx", 12, "l"), ("wrapped_adv.tsx", 13, "N"), ("wrapped_adv.tsx", 14, "O"),
        ("wrapped_adv.tsx", 17, "R"),
    ],
    ("js-exported-constants", "javascript"): [
        ("adv.js", 1, "A"), ("adv.js", 2, "b"), ("adv.js", 8, "J"), ("plain.js", 6, "arrow"),
        ("wrapped.jsx", 1, "A"), ("wrapped.jsx", 2, "B"), ("wrapped.jsx", 3, "c"),
    ],
    ("js-exported-arrow-functions", "typescript"): [
        ("adv.ts", 10, "B2"), ("adv.ts", 11, "lower"), ("decls.ts", 9, "handler"),
        ("decls.ts", 12, "typedArrow"), ("decls.ts", 13, "asyncArrow"),
        ("decls.ts", 14, "genericArrow"), ("decls.ts", 15, "annotated"), ("decls.ts", 16, "single"),
        ("decls.ts", 17, "Button"), ("decls.ts", 18, "AsyncPanel"), ("decls.ts", 52, "Ünit"),
        ("functions.ts", 38, "arrow"), ("tricky.ts", 49, "arrowish"),
    ],
    ("js-exported-arrow-functions", "tsx"): [
        ("adv.tsx", 2, "Jsx"), ("adv.tsx", 3, "helper"), ("adv.tsx", 9, "Gen"),
        ("components.tsx", 43, "Panel"), ("decls.tsx", 1, "Panel"), ("decls.tsx", 2, "Generic"),
        ("decls.tsx", 3, "Typed"), ("decls.tsx", 4, "AsyncCard"), ("decls.tsx", 5, "helper"),
    ],
    ("js-exported-arrow-functions", "javascript"): [
        ("adv.js", 1, "A"), ("adv.js", 2, "C"), ("adv.js", 8, "J"), ("plain.js", 6, "arrow"),
    ],
    ("js-exported-classes", "typescript"): [
        ("adv.ts", 37, "Angular"), ("adv.ts", 40, "Abs"), ("adv.ts", 41, "Over"),
        ("decls.ts", 23, "Store"), ("decls.ts", 24, "Box"), ("decls.ts", 27, "Child"),
        ("decls.ts", 28, "Base"), ("decls.ts", 30, "Decorated"), ("decls.ts", 31, "Inner"),
        ("functions.ts", 41, "Store"), ("tricky.ts", 44, "Decorated"),
    ],
    ("js-exported-classes", "tsx"): [
        ("adv.tsx", 15, "ObsStore"), ("components.tsx", 47, "Legacy"), ("decls.tsx", 12, "Widget"),
        ("tricky.tsx", 27, "Store"),
    ],
    ("js-exported-classes", "javascript"): [
        ("adv.js", 3, "B"), ("adv.js", 7, "H"),
    ],
    ("ts-exported-types", "typescript"): [
        ("adv.ts", 16, "Dir"), ("adv.ts", 39, "DeclaredProps"), ("decls.ts", 35, "ButtonProps"),
        ("decls.ts", 38, "IconProps"), ("decls.ts", 41, "ListProps"), ("decls.ts", 42, "Other"),
        ("decls.ts", 44, "AliasProps"), ("functions.ts", 45, "Api"), ("props.ts", 1, "ButtonProps"),
        ("types.ts", 1, "Plain"), ("types.ts", 2, "Ext"), ("types.ts", 3, "Gen"),
        ("types.ts", 4, "Alias"), ("types.ts", 5, "GenericAlias"), ("types.ts", 6, "Color"),
        ("types.ts", 7, "Flag"), ("types.ts", 8, "Declared"), ("types_adv.ts", 2, "DeclI"),
        ("types_adv.ts", 3, "DeclT"), ("types_adv.ts", 13, "Split"),
        ("types_adv.ts", 15, "Defaults"), ("types_adv.ts", 16, "Fn"),
        ("types_adv.ts", 17, "Mapped"), ("types_adv.ts", 18, "Commented"),
        ("types_adv.ts", 22, "DCE"),
    ],
    ("ts-exported-types", "tsx"): [
        ("adv.tsx", 20, "MultiLineProps"), ("components.tsx", 52, "CardProps"),
        ("decls.tsx", 9, "CardProps"),
    ],
    ("js-reexports", "typescript"): [
        ("adv.ts", 49, "one"), ("adv.ts", 50, "three"), ("adv.ts", 51, "strAlias"),
        ("adv.ts", 52, "quoted-out"), ("decls.ts", 45, "a"), ("decls.ts", 45, "c"),
        ("decls.ts", 46, "Widget"), ("decls.ts", 46, "WidgetProps"), ("decls.ts", 47, "ThemeProps"),
        ("decls.ts", 48, "default"), ("locals.ts", 2, "a"), ("types_adv.ts", 11, "Plain"),
    ],
    ("js-reexports", "tsx"): [
        ("adv.tsx", 17, "CardProps"), ("adv.tsx", 17, "default"), ("adv.tsx", 18, "Btn"),
        ("decls.tsx", 13, "Tile"), ("decls.tsx", 13, "TileProps"),
    ],
    ("js-reexports", "javascript"): [
        ("adv.js", 5, "f"), ("adv.js", 5, "g"),
    ],
    ("js-namespace-reexports", "typescript"): [
        ("adv.ts", 54, "nsC"), ("adv.ts", 55, "strNs"), ("decls.ts", 49, "ns"),
    ],
    ("js-namespace-reexports", "tsx"): [
        ("decls.tsx", 14, "icons"),
    ],
    ("js-namespace-reexports", "javascript"): [
        ("adv.js", 6, "h"),
    ],
    ("js-local-exports", "typescript"): [
        ("adv.ts", 58, "X"), ("decls.ts", 51, "MAX"), ("decls.ts", 51, "Shop"),
        ("functions.ts", 51, "internal"), ("locals.ts", 11, "default"), ("locals.ts", 12, "T"),
        ("locals.ts", 13, "TT"), ("locals.ts", 13, "y"), ("locals.ts", 16, "z"),
        ("locals.ts", 18, "str-out"), ("locals.ts", 19, "zed"), ("tricky.ts", 48, "aliased"),
        ("types_adv.ts", 21, "Local"),
    ],
    ("js-local-exports", "tsx"): [
        ("button.tsx", 10, "Button"), ("button.tsx", 10, "buttonVariants"), ("card.tsx", 9, "Card"),
        ("card.tsx", 9, "CardHeader"), ("dialog.tsx", 15, "Dialog"), ("dialog.tsx", 15, "DialogTrigger"),
        ("dialog.tsx", 16, "DialogProps"), ("dialog.tsx", 16, "DialogTriggerProps"), ("tricky.tsx", 37, "Renamed"),
    ],
    ("js-local-exports", "javascript"): [
        ("locals.js", 3, "y"), ("locals.js", 4, "str-out"), ("locals.js", 5, "why"),
        ("plain.js", 5, "hidden"),
    ],
    ("rust-public-functions", "rust"): [
        ("adv.rs", 6, "split_lines"), ("adv.rs", 9, "commented_vis"), ("adv.rs", 11, "r#match"),
        ("adv.rs", 12, "lifetimes"), ("adv.rs", 14, "cfg_gated"), ("adv.rs", 17, "deep_pub"),
        ("lib.rs", 1, "add"), ("lib.rs", 4, "reset"), ("lib.rs", 5, "fetch"), ("lib.rs", 6, "zero"),
        ("lib.rs", 7, "raw"), ("lib.rs", 8, "ffi_entry"), ("lib.rs", 9, "both"),
        ("lib.rs", 12, "map"), ("lib.rs", 45, "distance"),
    ],
    ("go-exported-functions", "go"): [
        ("adv.go", 9, "Split"), ("adv.go", 11, "Generic"), ("adv.go", 18, "Union"),
        ("adv.go", 20, "Constrained"), ("adv.go", 22, "Curried"), ("adv.go", 24, "Anon"),
        ("adv.go", 26, "Chan"), ("adv.go", 28, "Commented"), ("adv.go", 30, "ParamComment"),
        ("adv.go", 32, "Multi"), ("adv.go", 42, "Élan"), ("adv.go", 56, "Printf"),
        ("adv.go", 58, "GenBodyless"), ("comments.go", 3, "LineComments"),
        ("comments.go", 10, "AfterFunc"), ("comments.go", 12, "TP"),
        ("comments.go", 14, "TPComment"), ("comments.go", 16, "TPLine"),
        ("comments.go", 20, "BeforeResult"), ("comments.go", 22, "BeforeBody"),
        ("comments.go", 24, "NoParamsComment"), ("main.go", 3, "Exported"), ("main.go", 7, "Unit"),
        ("main.go", 10, "Pair"), ("main.go", 12, "Named"), ("main.go", 14, "Variadic"),
        ("main.go", 16, "Map"), ("main.go", 18, "Keys"), ("main.go", 20, "NoArgs"),
        ("main.go", 22, "Asm"), ("main.go", 25, "Documented"), ("main.go", 43, "Outer"),
    ],
    ("react-props-interfaces", "typescript"): [
        ("decls.ts", 35, "ButtonProps"), ("decls.ts", 38, "IconProps"),
        ("decls.ts", 41, "ListProps"), ("props.ts", 1, "ButtonProps"),
    ],
    ("react-props-interfaces", "tsx"): [
        ("adv.tsx", 20, "MultiLineProps"), ("components.tsx", 52, "CardProps"),
        ("decls.tsx", 9, "CardProps"),
    ],
    ("react-component-functions", "tsx"): [
        ("adv.tsx", 5, "Page"), ("components.tsx", 2, "Card"), ("components.tsx", 6, "Typed"),
        ("components.tsx", 10, "ServerList"), ("components.tsx", 14, "List"),
        ("components.tsx", 18, "Select"), ("components.tsx", 22, "App"),
        ("components.tsx", 27, "Poly"), ("components.tsx", 28, "Poly"), ("gen.tsx", 4, "Real"),
        ("tricky.tsx", 3, "Generic"), ("tricky.tsx", 7, "DefaultSplit"), ("tricky.tsx", 8, "GET"),
        ("tricky.tsx", 9, "URLBar"), ("tricky.tsx", 11, "Outer"), ("tricky.tsx", 16, "Over"),
        ("tricky.tsx", 17, "Over"), ("tricky.tsx", 21, "AfterOver"),
        ("tricky.tsx", 22, "DeclaredComp"), ("tricky.tsx", 28, "AfterDecorator"),
        ("tricky.tsx", 31, "Ünicode"), ("tricky.tsx", 33, "Multi"),
    ],
    ("react-component-functions", "typescript"): [
        ("functions.ts", 23, "Main"),
    ],
    ("react-component-functions", "javascript"): [
        ("comp.jsx", 1, "JsxCard"), ("comp.jsx", 2, "JsxApp"), ("comp.jsx", 4, "Élan"),
        ("plain.js", 2, "JsDefault"),
    ],
    ("react-component-arrow-functions", "typescript"): [
        ("adv.ts", 10, "B2"), ("adv.ts", 11, "Upper"), ("decls.ts", 17, "Button"),
        ("decls.ts", 18, "AsyncPanel"), ("decls.ts", 52, "Ünit"),
    ],
    ("react-component-arrow-functions", "tsx"): [
        ("adv.tsx", 2, "Jsx"), ("adv.tsx", 3, "Comp"), ("adv.tsx", 9, "Gen"),
        ("components.tsx", 43, "Panel"), ("decls.tsx", 1, "Panel"), ("decls.tsx", 2, "Generic"),
        ("decls.tsx", 3, "Typed"), ("decls.tsx", 4, "AsyncCard"),
    ],
    ("react-component-arrow-functions", "javascript"): [
        ("adv.js", 1, "A"), ("adv.js", 2, "C"), ("adv.js", 8, "J"),
    ],
    ("react-wrapped-components", "tsx"): [
        ("adv.tsx", 4, "Fwd"), ("adv.tsx", 22, "Lazy"), ("decls.tsx", 8, "Memo"),
        ("tricky.tsx", 15, "Wrapped"), ("wrapped.tsx", 1, "Memoed"),
        ("wrapped.tsx", 2, "Forwarded"), ("wrapped.tsx", 3, "Lazy"), ("wrapped_adv.tsx", 1, "A"),
        ("wrapped_adv.tsx", 2, "B"), ("wrapped_adv.tsx", 3, "C"), ("wrapped_adv.tsx", 4, "D"),
        ("wrapped_adv.tsx", 11, "J"), ("wrapped_adv.tsx", 12, "M"), ("wrapped_adv.tsx", 17, "R"),
    ],
    ("react-wrapped-components", "typescript"): [
        ("decls.ts", 19, "Wrapped"),
    ],
    ("react-wrapped-components", "javascript"): [
        ("wrapped.jsx", 1, "A"), ("wrapped.jsx", 2, "B"),
    ],
    ("vue-define-props", "typescript"): [
        ("A.vue", 2, "SingleQuoted"), ("B.vue", 7, "SecondBlock"),
        ("Button.vue", 3, "VueButtonProps"), ("D.vue", 3, "GenericComp<T>"),
        ("D.vue", 4, "PlainInGeneric"), ("F.vue", 5, "MultiLineTag"), ("G.vue", 3, "TemplateFirst"),
        ("H.vue", 2, "UpperLang"), ("J.vue", 2, "LangFirst"), ("props.ts", 7, "ButtonProps"),
        ("props.ts", 9, "CardProps"), ("props.ts", 11, "Local"), ("props.ts", 13, "ButtonProps"),
        ("props.ts", 15, "{ size: number }"), ("props.ts", 17, "Types.PanelProps"),
        ("props.ts", 19, "Wrapper<Inner>"), ("props_adv.ts", 4, "InSubst"),
        ("props_adv.ts", 5, "Spaced"), ("props_adv.ts", 7, "MultiLine"),
        ("props_adv.ts", 9, "CommentArg"), ("props_adv.ts", 12, "typeof runtimeObj"),
        ("props_adv.ts", 13, "A | B"), ("props_adv.ts", 14, "Item[]"),
        ("props_adv.ts", 15, "Omit<Props, \"x\">"), ("props_adv.ts", 21, "NonNull"),
        ("props_adv.ts", 22, "AsCast"), ("props_adv.ts", 25, "Props<T>"),
        ("props_adv.ts", 27, "keyof Foo"), ("props_adv.ts", 28, "\"literal\""),
        ("props_adv.ts", 29, "A & B"), ("props_adv.ts", 30, "[A]"),
        ("props_adv.ts", 31, "(Parened)"),
    ],
    ("vue-define-props-tsx", "tsx"): [
        ("C.vue", 2, "TsxLang"), ("K.vue", 2, "{ size: number }"), ("K.vue", 4, "Types.TsxProps"),
    ],
}



def _recipes() -> list[tuple[str, str, dict]]:
    """(file relative to REFS, fenced text, parsed recipe) for every recipe."""
    found = []
    for md in sorted(REFS.rglob("*.md")):
        for block in FENCE_RE.findall(md.read_text(encoding="utf-8")):
            # A recipe starts with `id:` after any comment lines; other yaml
            # blocks in the step files are templates, not always valid YAML.
            body = [ln for ln in block.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
            if not body or not body[0].startswith("id:"):
                continue
            doc = yaml.safe_load(block)
            assert isinstance(doc, dict) and {"id", "language", "rule"} <= set(doc), block
            found.append((md.relative_to(REFS).as_posix(), block, doc))
    return found


RECIPES = _recipes()


def _with_language(block: str, language: str) -> str:
    """The recipe with its `language:` line rewritten, as the language notes say."""
    out, n = re.subn(r"^language: .*$", f"language: {language}", block, count=1, flags=re.M)
    assert n == 1, block
    return out


def _runs() -> list[tuple[str, str, dict, str]]:
    """(file, recipe text, parsed recipe, language) for every recipe block and
    every other language its notes run it with."""
    runs = []
    for md, block, doc in RECIPES:
        runs.append((md, block, doc, doc["language"]))
        for language in VARIANTS.get((doc["id"], doc["language"]), ()):
            runs.append((md, _with_language(block, language), doc, language))
    return runs


RUNS = _runs()

# The recipe file the runner reads: a mapping whose `recipes` list holds them,
# one YAML document, as lint:instructions (lintlang) parses every YAML file.
DATA_RECIPES = yaml.safe_load(DATA_FILE.read_text(encoding="utf-8"))["recipes"]


def _recipe_id(item: tuple[str, str, dict]) -> str:
    return f"{item[0]}:{item[2]['id']}:{item[2]['language']}"


def _run_id(run: tuple[str, str, dict, str]) -> str:
    return f"{run[0]}:{run[2]['id']}:{run[3]}"


def _binds_name(node: object) -> bool:
    """True when a `pattern` in the rule, outside any `not:`, captures `$NAME`."""
    if isinstance(node, dict):
        return any(
            (key == "pattern" and isinstance(value, str) and "$NAME" in value)
            or (key != "not" and _binds_name(value))
            for key, value in node.items()
        )
    if isinstance(node, list):
        return any(_binds_name(value) for value in node)
    return False


def test_every_recipe_is_known() -> None:
    ids = [doc["id"] for _, _, doc in RECIPES]
    # 20 in extraction-patterns.md (js-exported-functions and
    # react-component-functions twice: their typescript/tsx and javascript
    # forms); component-extraction.md names its recipes and holds no copy
    assert len(ids) == 20
    assert {md for md, _, _ in RECIPES} == {"extraction-patterns.md"}
    assert set(ids) == set(KINDS), f"a recipe without a verified kind: {sorted(set(ids) ^ set(KINDS))}"
    assert set(VARIANTS) <= {(doc["id"], doc["language"]) for _, _, doc in RECIPES}
    assert {(doc["id"], language) for _, _, doc, language in RUNS} == set(EXPECTED)
    assert all(EXPECTED.values()), "every run has matches to find in the fixtures"


@pytest.mark.parametrize("item", RECIPES, ids=_recipe_id)
def test_recipe_rule_names_its_kind(item: tuple[str, str, dict]) -> None:
    _, _, doc = item
    assert doc["rule"].get("kind") == KINDS[doc["id"]]
    assert _binds_name(doc["rule"]), "no pattern outside `not:` captures $NAME"


def test_data_file_holds_the_markdown_recipes() -> None:
    """The runner's recipe file and extraction-patterns.md hold the same
    rules, form for form; the file adds only each recipe's metadata."""
    markdown = {(doc["id"], doc["language"]): doc for _, _, doc in RECIPES}
    data = {(doc["id"], doc["language"]): doc for doc in DATA_RECIPES}
    assert len(data) == len(DATA_RECIPES), "a recipe form twice in the data file"
    assert set(data) == set(markdown)
    for key, doc in data.items():
        assert set(doc) <= {"id", "language", "metadata", "rule", "constraints"}, key
        assert doc["rule"] == markdown[key]["rule"], key
        assert doc.get("constraints") == markdown[key].get("constraints"), key


def _slice(text: str, start: str, end: str) -> str:
    assert text.count(start) == 1, start
    head = text.index(start)
    tail = text.index(end, head)
    return text[head:tail]


def _fenced_ids(text: str) -> set[str]:
    return {yaml.safe_load(block)["id"] for block in FENCE_RE.findall(text) if block.startswith("id:")}


def _named_ids(text: str) -> set[str]:
    """The recipe ids a passage names in backticks."""
    return {name for name in re.findall(r"`([a-z][a-z-]+)`", text) if name in KINDS}


def _component_steps() -> dict[int, str]:
    """component-extraction.md's Phase 4 steps, by number."""
    phase = _slice(COMPONENT_EXTRACTION.read_text(encoding="utf-8"), "### Phase 4: Props-First Extraction",
                   "### Phase 5")
    marks = [phase.index(f"**Step {n} ") for n in (1, 2, 3, 4)] + [len(phase)]
    return {n: phase[marks[n - 1]:marks[n]] for n in (1, 2, 3, 4)}


def test_data_file_metadata_matches_the_prose() -> None:
    """Each recipe runs in the languages the fixture runs cover (VARIANTS),
    belongs to the sets the prose runs it in (the standard flow runs the
    by-language recipes, component-extraction.md Phase 4 the ones it names,
    every Component Library recipe among them), and names an export type the
    runner knows; prefer_over names recipes that share a language with it."""
    patterns = PATTERNS.read_text(encoding="utf-8")
    by_language = _fenced_ids(_slice(patterns, "### YAML Rule Recipes by Language",
                                     "### Component Library YAML Rule Recipes"))
    components = _fenced_ids(_slice(patterns, "### Component Library YAML Rule Recipes",
                                    "### Known ast-grep Limitations"))
    named = set().union(*(_named_ids(step) for step in _component_steps().values()))
    languages: dict[str, set[str]] = {}
    for doc in DATA_RECIPES:
        meta = doc["metadata"]
        assert meta["languages"] == [doc["language"], *VARIANTS.get((doc["id"], doc["language"]), ())], doc["id"]
        languages.setdefault(doc["id"], set()).update(meta["languages"])
        types = meta["export_type"] if isinstance(meta["export_type"], list) else [meta["export_type"]]
        assert set(types) <= EXPORT_TYPES, doc["id"]
    for doc in DATA_RECIPES:
        for loser in doc["metadata"].get("prefer_over", []):
            assert loser in languages and languages[loser] & languages[doc["id"]], (doc["id"], loser)
    standard = {doc["id"] for doc in DATA_RECIPES if "standard" in doc["metadata"]["sets"]}
    component = {doc["id"] for doc in DATA_RECIPES if "component-library" in doc["metadata"]["sets"]}
    assert standard == by_language | VUE_RECIPES
    assert component == named and components <= named


def test_runner_rules_match_the_prose() -> None:
    """The runner restates three rules of extraction-patterns.md: the head
    cap selection (HEAD_CAPS), the dedupe priority (prefer_over) and the
    language selection note (metadata.languages). Each copy agrees with the
    prose it restates."""
    runner = _runner()
    text = PATTERNS.read_text(encoding="utf-8")
    flat = " ".join(text.split())
    default = re.search(r"\*\*Default \(Quick/Forge, any scope\):\*\* `N = (\d+)`", flat)
    assert default is not None and int(default.group(1)) == runner.DEFAULT_HEAD_CAP
    caps = {(tier, scope): int(cap) for tiers, scope, cap in re.findall(
        r"\*\*(Forge\+/Deep) with `scope\.type: \"([a-z-]+)\"`:\*\* `N = (\d+)`", flat) for tier in tiers.split("/")}
    assert caps == runner.HEAD_CAPS

    prefer: dict[str, set[str]] = {}
    languages: dict[str, set[str]] = {}
    forms: dict[str, set[str]] = {}
    for doc in DATA_RECIPES:
        prefer.setdefault(doc["id"], set()).update(doc["metadata"].get("prefer_over", []))
        languages.setdefault(doc["id"], set()).update(doc["metadata"]["languages"])
        forms.setdefault(doc["id"], set()).add(doc["language"])
    words = {"arrow function match": "js-exported-arrow-functions",
             "function declaration match": "js-exported-functions", "constant match": "js-exported-constants"}
    priority = re.search(r"Priority when deduplicating: ([^.]+)\.", flat)
    assert priority is not None
    ranked = [words[part.strip()] for part in priority.group(1).split(">")]
    for i, winner in enumerate(ranked):
        assert not any(winner in prefer[loser] for loser in ranked[i + 1:]), winner
    # the two of them that match one name on one line: `export const f = () => ...`
    assert "js-exported-constants" in prefer["js-exported-arrow-functions"]

    note = re.search(r"> \*\*Language selection:\*\*(.*?)\n\n", text, re.S)
    assert note is not None
    unchanged = _named_ids(_slice(note.group(1), "`language: javascript`:", "run unchanged"))
    js_forms = _named_ids(_slice(note.group(1), "run unchanged", "have `javascript` forms"))
    ts_only = _named_ids(_slice(note.group(1), "have `javascript` forms", "are TypeScript only"))
    assert unchanged | js_forms | ts_only == {rid for rid in languages if rid not in VUE_RECIPES
                                               and languages[rid] & {"typescript", "tsx", "javascript"}}
    js_ts = {"typescript", "tsx", "javascript"}
    assert all(languages[rid] == js_ts and len(forms[rid]) == 1 for rid in unchanged), unchanged
    assert all(languages[rid] == js_ts and "javascript" in forms[rid] for rid in js_forms), js_forms
    assert all(languages[rid] == {"typescript", "tsx"} for rid in ts_only), ts_only


def test_component_extraction_names_its_recipes() -> None:
    """Phase 4 names its recipes by id and holds no copy of one; the retired
    `react-component-exports` alias is gone (#559)."""
    text = COMPONENT_EXTRACTION.read_text(encoding="utf-8")
    assert not [block for block in FENCE_RE.findall(text) if block.lstrip().startswith(("id:", "#"))]
    steps = _component_steps()
    assert _named_ids(steps[1]) == {"react-props-interfaces", "vue-define-props", "vue-define-props-tsx"}
    assert _named_ids(steps[2]) == {"react-component-functions", "react-component-arrow-functions",
                                    "react-wrapped-components", "js-local-exports"}
    assert _named_ids(steps[4]) == {"ts-exported-types"}
    assert "$NAME" not in steps[4], "Step 4 runs a recipe, not bare patterns"
    for md in (REPO / "src").rglob("*.md"):
        assert "react-component-exports" not in md.read_text(encoding="utf-8"), md


def _found(recipe_ids: set[str], files: set[str]) -> set[str]:
    return {name for (recipe_id, _), matches in EXPECTED.items() if recipe_id in recipe_ids
            for file, _, name in matches if file in files}


def test_component_extraction_step_2_finds_the_issue_components() -> None:
    """#559's shadcn/ui shapes: the recipes Step 2 names find every
    component and shared export of button.tsx, card.tsx and wrapped.tsx."""
    found = _found(_named_ids(_component_steps()[2]), {"button.tsx", "card.tsx", "wrapped.tsx"})
    assert found == {"Button", "buttonVariants", "Card", "CardHeader", "Memoed", "Forwarded", "Lazy"}


def test_component_extraction_step_2_sorts_a_radix_list() -> None:
    """A Radix primitive declares its Props interfaces unexported and lists
    them in `export type { ... }`: Step 1's recipes find none of them, Step
    2's find them all, and Step 2 sorts a type-only item ending in Props
    into the Props contracts, not the components."""
    steps = _component_steps()
    assert _found(_named_ids(steps[1]), {"dialog.tsx"}) == set()
    assert _found(_named_ids(steps[2]), {"dialog.tsx"}) == {"Dialog", "DialogTrigger", "DialogProps",
                                                            "DialogTriggerProps"}
    step_2 = " ".join(steps[2].split())
    assert ("A type-only item (one in an `export type { ... }` list, or a `type X` specifier) is a type: "
            "one whose name ends in `Props` is a Props contract for Steps 1 and 3") in step_2
    assert "A PascalCase value item is a component" in step_2


def test_component_extraction_step_4_finds_the_types() -> None:
    """Step 4's recipe finds the generic, `extends` and `declare` forms the
    bare patterns missed, and no namespace member (#559)."""
    found = _found(_named_ids(_component_steps()[4]), {"types.ts"})
    assert {"Ext", "Gen", "GenericAlias", "Declared"} <= found
    assert found.isdisjoint({"Inner", "InnerT", "InnerE"})
    assert found == {"Plain", "Ext", "Gen", "Alias", "GenericAlias", "Color", "Flag", "Declared"}


def test_inline_find_code_by_rule_example_matches_the_python_recipe() -> None:
    (inline,) = INLINE_RULE_RE.findall(PATTERNS.read_text(encoding="utf-8"))
    doc = yaml.safe_load(json.loads(f'"{inline}"'))
    assert doc["rule"]["kind"] == "function_definition"
    (python,) = [d for f, _, d in RECIPES if d["id"] == "python-public-functions"]
    assert doc["rule"] == python["rule"]
    assert doc["constraints"] == python["constraints"]


def test_cli_template_runs_a_recipe_and_prints_its_kind() -> None:
    text = PATTERNS.read_text(encoding="utf-8")
    (code,) = CLI_TEMPLATE_RE.findall(text)
    assert "RECIPE = '{recipe_id}'" in code
    assert "KIND = '{node_kind}'" in code
    # the line is $NAME's, not the match's first line
    assert "ln = v['NAME'].get('range',{}).get('start',{}).get('line',0)+1" in code
    assert "print(f'[AST:{f}:L{ln}] {RECIPE} kind={KIND} name={name}'" in code


# --------------------------------------------------------------------------
# Real ast-grep runs
# --------------------------------------------------------------------------


def _ast_grep() -> str | None:
    exe = shutil.which("ast-grep")
    if exe is None:
        return None
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, text=True,
                             timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return exe if out.returncode == 0 and out.stdout.split()[-1:] == [PINNED_VERSION] else None


AST_GREP = _ast_grep()
needs_ast_grep = pytest.mark.skipif(AST_GREP is None, reason=f"no ast-grep {PINNED_VERSION} binary on PATH")

# The Vue note's scratch config: maps .vue files to HTML.
SGCONFIG = 'languageGlobs:\n  html: ["*.vue"]\n'


@pytest.fixture(scope="module")
def fixture_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("recipes")
    for name, text in FIXTURES.items():
        # bytes, so the fixtures keep their LF line ends on Windows too
        (root / name).write_bytes(text.encode("utf-8"))
    return root


def _scan(exe: str, block: str, root: Path, rule_dir: Path) -> str:
    """ast-grep's --json=stream output for one recipe over the fixtures,
    with the rule and the sgconfig.yml in a scratch folder."""
    rule = rule_dir / "recipe.yml"
    rule.write_text(block, encoding="utf-8")
    config = rule_dir / "sgconfig.yml"
    config.write_text(SGCONFIG, encoding="utf-8")
    result = subprocess.run(
        [exe, "scan", "-c", str(config), "-r", str(rule), "--json=stream", "."],
        capture_output=True, text=True, encoding="utf-8", check=False, cwd=root,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def _matches(exe: str, block: str, root: Path, rule_dir: Path) -> list[tuple[str, int, str]]:
    """Sorted (file, $NAME's 1-based line, $NAME) for every match."""
    found = []
    for line in _scan(exe, block, root, rule_dir).splitlines():
        name = json.loads(line)["metaVariables"]["single"]["NAME"]
        found.append((Path(json.loads(line)["file"]).name, name["range"]["start"]["line"] + 1, name["text"]))
    return sorted(found)


@needs_ast_grep
@pytest.mark.parametrize("run", RUNS, ids=_run_id)
def test_recipe_matches_on_fixtures(run: tuple[str, str, dict, str], fixture_dir: Path, tmp_path: Path) -> None:
    _, block, doc, language = run
    assert _matches(AST_GREP, block, fixture_dir, tmp_path) == EXPECTED[(doc["id"], language)]


@needs_ast_grep
@pytest.mark.parametrize("run", RUNS, ids=_run_id)
def test_another_kind_loses_the_matches(run: tuple[str, str, dict, str], fixture_dir: Path, tmp_path: Path) -> None:
    """The declared kind is the matched node's: a neighbouring kind matches nothing."""
    _, block, doc, _ = run
    kind = KINDS[doc["id"]]
    wrong = block.replace(f"kind: {kind}", f"kind: {NEIGHBOUR_KINDS[kind]}", 1)
    assert wrong != block
    assert yaml.safe_load(wrong)["rule"]["kind"] == NEIGHBOUR_KINDS[kind]
    assert _matches(AST_GREP, wrong, fixture_dir, tmp_path) == []


def _verifier():
    """src/shared/scripts/skf-verify-provenance-completeness.py, loaded as a module."""
    path = REPO / "src" / "shared" / "scripts" / "skf-verify-provenance-completeness.py"
    spec = importlib.util.spec_from_file_location("skf_verify_provenance_completeness", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# The Vue recipes' $NAME is the props type a call names, defined elsewhere, so
# its line is a use, not a definition.
NOT_DEFINITIONS = {"vue-define-props", "vue-define-props-tsx"}

def test_expected_lines_are_definition_lines(fixture_dir: Path) -> None:
    """Each Python / TS / JS line EXPECTED cites is one the provenance
    verifier (`find_definition_lines`) accepts: later declarators, string
    names in re-exports, a name on the line after its keyword and a
    decorator on the `export` line included (#560)."""
    verifier = _verifier()
    unread = []
    for (recipe_id, _), matches in EXPECTED.items():
        if recipe_id in NOT_DEFINITIONS:
            continue
        for file, line, name in matches:
            lines = verifier.find_definition_lines(file, name, fixture_dir)
            if lines is None:
                continue  # no definition rule for this extension (.rs, .go, .vue)
            if line not in lines:
                unread.append((recipe_id, file, line, name, lines))
    assert unread == []


@needs_ast_grep
@pytest.mark.parametrize("source", [PATTERNS, DATA_FILE], ids=["markdown", "data-file"])
def test_kind_at_gives_each_recipe_kind(source: Path, fixture_dir: Path) -> None:
    """The provenance verifier's kind-at, reading extraction-patterns.md or
    the runner's recipe file, gives the kind the matching recipe declares at
    every Python / TS / JS / Rust / Go line EXPECTED cites (a Vue recipe's
    $NAME is a type, so its lines are looked up by line alone)."""
    verifier = _verifier()
    recipes = verifier.load_recipes(source)
    wanted: dict[str, dict[tuple[int, str | None], set[str]]] = {}
    for (recipe_id, _), matches in EXPECTED.items():
        for file, line, name in matches:
            if verifier.ast_grep_language(file) is None:
                continue  # .vue: read as HTML through an sgconfig.yml
            target = (line, None if recipe_id in NOT_DEFINITIONS else name)
            wanted.setdefault(file, {}).setdefault(target, set()).add(KINDS[recipe_id])
    wrong = []
    for file, targets in sorted(wanted.items()):
        order = sorted(targets, key=lambda t: (t[0], t[1] or ""))
        results = verifier.kinds_at((fixture_dir / file).read_bytes(),
                                    verifier.ast_grep_language(file), order, recipes)
        for target, result in zip(order, results):
            if result["status"] != "found" or {result["kind"]} != targets[target]:
                wrong.append((file, target, result["status"], result["kind"], targets[target]))
    assert wrong == []


@needs_ast_grep
@pytest.mark.parametrize(
    ("recipe_id", "wanted"),
    [
        # a decorated class: the line and the signature are the class's, not the decorator's
        ("js-exported-classes", "decls.ts:L30] js-exported-classes kind=export_statement name=Decorated export class Decorated {}"),
        # a re-exported name: its own specifier, with the module it comes from
        ("js-reexports", "decls.ts:L45] js-reexports kind=export_specifier name=c from=./x b as c"),
    ],
)
def test_cli_template_cites_the_name_line(recipe_id: str, wanted: str, fixture_dir: Path, tmp_path: Path) -> None:
    (code,) = CLI_TEMPLATE_RE.findall(PATTERNS.read_text(encoding="utf-8"))
    (_, block, doc) = [r for r in RECIPES if r[2]["id"] == recipe_id][0]
    code = (code.replace("{exclude_patterns}", "[]").replace("{recipe_id}", recipe_id)
            .replace("{node_kind}", KINDS[recipe_id]))
    stream = _scan(AST_GREP, block, fixture_dir, tmp_path)
    out = subprocess.run([sys.executable, "-c", code], input=stream, capture_output=True,
                         text=True, encoding="utf-8", check=True).stdout
    assert any(line.startswith("[AST:") and line.endswith(wanted) for line in out.splitlines()), out


# --------------------------------------------------------------------------
# The recipe runner over the fixtures
# --------------------------------------------------------------------------


def _runner():
    """src/shared/scripts/skf-extract-public-api.py, loaded as a module."""
    spec = importlib.util.spec_from_file_location("skf_extract_public_api_recipes", RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _expected_exports(recipe_set: str) -> list[tuple[str, int, str, str]]:
    """The exports the recipes of `recipe_set` give the fixtures: each name
    of each file once, at its first line, with the kind the recipes that
    match that line declare (a name starting with `_` is never an export)."""
    ids = {doc["id"] for doc in DATA_RECIPES if recipe_set in doc["metadata"]["sets"]}
    lines: dict[tuple[str, str], dict[int, set[str]]] = {}
    for (recipe_id, _), matches in EXPECTED.items():
        if recipe_id not in ids:
            continue
        for file, line, name in matches:
            if not name.startswith("_"):
                lines.setdefault((file, name), {}).setdefault(line, set()).add(KINDS[recipe_id])
    expected = []
    for (file, name), kinds_by_line in lines.items():
        first = min(kinds_by_line)
        (kind,) = kinds_by_line[first]
        expected.append((file, first, name, kind))
    return sorted(expected)


@needs_ast_grep
@pytest.mark.parametrize("recipe_set", ["standard", "component-library"])
def test_runner_output_on_fixtures(recipe_set: str, fixture_dir: Path, capsys: pytest.CaptureFixture) -> None:
    """skf-extract-public-api.py --mode full gives exactly the (file, line,
    name, kind) the recipes' matches give, and counts each recipe's matches
    (#584)."""
    runner = _runner()
    code = runner.main(["--mode", "full", "--source-root", str(fixture_dir), "--recipe-set", recipe_set,
                        "--head-cap", "0"])
    out = json.loads(capsys.readouterr().out)
    assert (code, out["status"], out["errors"]) == (0, "ok", [])
    got = sorted((e["source_file"], e["source_line"], e["export_name"], e["ast_node_type"]) for e in out["exports"])
    assert got == _expected_exports(recipe_set)
    counts = {r["id"]: r["matches"] for r in out["recipes"]}
    for recipe_id, count in counts.items():
        assert count == sum(1 for (i, _), matches in EXPECTED.items() if i == recipe_id
                            for _, _, name in matches if not name.startswith("_")), recipe_id
    assert out["files_in_scope"] == len(FIXTURES)
    recipes = {(e["source_file"], e["export_name"]): e["ast_recipe"] for e in out["exports"]}
    if recipe_set == "standard":
        # an arrow function wins over the constant it also is
        assert recipes[("decls.ts", "handler")] == "js-exported-arrow-functions"
        assert recipes[("decls.ts", "LIMIT")] == "js-exported-constants"
    else:
        # a Props interface wins over the type it also is
        assert recipes[("decls.ts", "ButtonProps")] == "react-props-interfaces"
        assert recipes[("decls.ts", "Other")] == "ts-exported-types"
        assert recipes[("button.tsx", "Button")] == "js-local-exports"
        # a local list's item takes the type of what it names
        types = {(e["source_file"], e["export_name"]): e["export_type"] for e in out["exports"]}
        assert [types[("dialog.tsx", name)] for name in ("Dialog", "DialogTrigger", "DialogProps")] == [
            "function", "const", "interface"]
