import { YangModule } from "../core/model";
import { YangExportError } from "../core/errors";
import { generateJsonSchema } from "./generator";
type Obj = Record<string, unknown>;
const object = (v: unknown): Obj => v && typeof v === "object" && !Array.isArray(v) ? v as Obj : {};
const array = (v: unknown): unknown[] => Array.isArray(v) ? v : [];
const PREFIXES: Record<string,string> = {
  schema: "https://schema.org/", rdf: "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
  rdfs: "http://www.w3.org/2000/01/rdf-schema#", skos: "http://www.w3.org/2004/02/skos/core#",
  wd: "http://www.wikidata.org/entity/"
};
const LEGACY: Record<string,string> = { "schema-org-property": "iri", "schema-org-class": "class", wikidata: "close-match", "unit-code": "unit-code" };
const namespace = (ns: string): string => /[#/:]$/.test(ns) ? ns : ns + "#";
const same = (a: unknown,b: unknown): boolean => JSON.stringify(a) === JSON.stringify(b);
class Builder {
  private readonly xy: Obj;
  private readonly module: string;
  private readonly base: string;
  private readonly namespaces: Record<string,string>;
  private readonly owners: Record<string,string>;
  private readonly graph = new Map<string,Obj>();
  constructor(private readonly schema: Obj) {
    this.xy = object(schema["x-yang"]);
    this.module = String(this.xy.module);
    this.base = namespace(String(this.xy.namespace || `urn:${this.module}`));
    this.namespaces = Object.assign(Object.create(null), { [this.module]: this.base });
    this.owners = Object.assign(Object.create(null), { [String(this.xy.prefix)]: this.module });
    for (const [prefix,raw] of Object.entries(object(this.xy.imports))) {
      const stub = object(raw), name = String(stub.module);
      this.namespaces[name] = namespace(String(stub.namespace || `urn:${name}`));
      this.owners[prefix] = name;
    }
  }
  private iri(value: string): string {
    const colon = value.indexOf(":");
    const prefix = value.slice(0,colon);
    if (colon >= 0 && PREFIXES[prefix]) value = PREFIXES[prefix] + value.slice(colon+1);
    if (/^[A-Za-z][A-Za-z0-9+.-]*:[^\s]+$/.exec(value)?.[0] !== value) throw new YangExportError(`JSON-LD mapping must be an absolute IRI: ${value}`);
    return value;
  }
  private mappings(node: Obj): Obj {
    const out: Obj = {};
    for (const raw of array(object(node["x-yang"]).extensions)) {
      const ext = object(raw), label = String(ext.name), colon = label.indexOf(":"), prefix = label.slice(0,colon), name = label.slice(colon+1);
      const key = this.owners[prefix] === "xyang-jsonld" ? name : LEGACY[name];
      if (!["iri","iri-value","class","close-match","unit-code"].includes(key)) continue;
      let argument = String(ext.argument ?? ""), value: unknown;
      if (key !== "iri-value" && !argument) throw new YangExportError(`JSON-LD ${key} mapping requires a non-empty argument`);
      if (key === "iri-value") value = true;
      else if (key === "unit-code") value = argument;
      else {
        if (["schema-org-property","schema-org-class"].includes(name) && !argument.includes(":")) argument = PREFIXES.schema + argument;
        if (name === "wikidata" && /^Q[0-9]+$/.test(argument)) argument = PREFIXES.wd + argument;
        value = key === "iri" && ["@id","@type"].includes(argument) ? argument : this.iri(argument);
      }
      if (key === "close-match") out[key] = [...array(out[key]),value];
      else if (key in out && !same(out[key],value)) throw new YangExportError(`Conflicting JSON-LD ${key} mappings`);
      else out[key] = value;
      if (name === "schema-org-property" && argument === PREFIXES.schema + "url") out["iri-value"] = true;
    }
    return out;
  }
  private resolve(node: Obj, seen = new Set<string>()): Obj {
    if (!node.$ref) return node;
    const ref = String(node.$ref);
    if (!ref.startsWith("#/$defs/") || seen.has(ref)) throw new YangExportError(`Unsupported or recursive JSON-LD schema reference: ${ref}`);
    const key = ref.slice("#/$defs/".length).replaceAll("~1","/").replaceAll("~0","~");
    const target = object(this.schema.$defs)[key];
    if (!target || typeof target !== "object") throw new YangExportError(`Unresolved JSON-LD schema reference: ${ref}`);
    const { $ref: _, ...rest } = node;
    return { ...this.resolve(object(target),new Set([...seen,ref])), ...rest };
  }
  private properties(shape: Obj): [string,Obj][] {
    shape = this.resolve(shape);
    const props: [string,Obj][] = Object.entries(object(shape.properties)).map(([key,v]) => [key,object(v)]);
    for (const key of ["oneOf","anyOf","allOf"]) for (const child of array(shape[key])) props.push(...this.properties(object(child)));
    return props;
  }
  private record(iri: string,name: string,node: Obj,mapping: Obj): void {
    if (iri.startsWith("@")) return;
    const record = this.graph.get(iri) ?? { "@id": iri,"@type":"rdf:Property","rdfs:label":name };
    this.graph.set(iri,record);
    const values: Obj = {"rdfs:label":name};
    if (node.description) values["rdfs:comment"] = node.description;
    const units = mapping["unit-code"] || object(node["x-yang"]).units;
    if (units) values["schema:unitCode"] = units;
    if (mapping.class) values["rdfs:range"] = { "@id": mapping.class };
    if (mapping["close-match"]) values["skos:closeMatch"] = array(mapping["close-match"]).map((iri) => ({"@id":iri}));
    for (const [key,value] of Object.entries(values)) {
      if (!(key in record)) record[key] = value;
      else if (!same(record[key],value)) {
        const old = Array.isArray(record[key]) ? record[key] as unknown[] : [record[key]];
        const next = Array.isArray(value) ? value : [value];
        record[key] = [...old,...next.filter((v) => !old.some((o) => same(o,v)))];
      }
    }
  }
  private terms(shape: Obj,parentModule: string,depth = 0): Obj {
    if (depth > 128) throw new YangExportError("JSON-LD context nesting exceeds 128 levels");
    const context: Obj = Object.create(null);
    for (const [key,raw] of this.properties(shape)) {
      const node = this.resolve(raw), colon = key.indexOf(":"), owner = colon >= 0 ? key.slice(0,colon) : parentModule, local = colon >= 0 ? key.slice(colon+1) : key;
      if (!(owner in this.namespaces)) throw new YangExportError(`JSON-LD namespace is missing for module ${owner}`);
      const mapping = this.mappings(node), iri = String(mapping.iri || this.namespaces[owner] + local);
      const term: Obj = { "@id": iri };
      if (mapping["iri-value"] && iri.startsWith("@")) throw new YangExportError("JSON-LD keyword aliases cannot have value coercion");
      if (mapping["iri-value"]) term["@type"] = "@id";
      const kind = object(node["x-yang"]).type;
      if (kind === "container" || kind === "list") {
        term["@context"] = this.terms(kind === "list" ? object(node.items) : node,owner,depth+1);
        if (iri.startsWith("@")) throw new YangExportError("JSON-LD keyword aliases cannot have child contexts");
      }
      if (colon >= 0 && iri !== this.namespaces[owner] + local) throw new YangExportError(`JSON-LD cannot remap compact-IRI member ${key}; use unqualified members`);
      if (key in context && !same(context[key],term)) throw new YangExportError(`Conflicting JSON-LD term ${key} across choice branches`);
      context[key] = term;
      this.record(iri,local,node,mapping);
    }
    return context;
  }
  build(): [Obj,Obj] {
    const terms = this.terms(this.schema,this.module);
    const context: Obj = Object.assign(Object.create(null), {"@version":1.1,"@vocab":this.base});
    for (const [owner,ns] of Object.entries(this.namespaces)) if (!(owner in terms)) context[owner] = {"@id":ns,"@prefix":true};
    Object.assign(context,terms);
    const vocab = {"@context":{"@version":1.1,...PREFIXES},"@graph":[...this.graph.keys()].sort().map((key) => this.graph.get(key))};
    return [{"@context":context},vocab];
  }
}
export function generateJsonldContext(module: YangModule): Obj { return new Builder(generateJsonSchema(module).schema).build()[0]; }
export function generateJsonldVocab(module: YangModule): Obj { return new Builder(generateJsonSchema(module).schema).build()[1]; }
