#!/usr/bin/env python3
"""Deterministic Robotomail bindings from the checked-in public API contract.

Only models and operation bindings are generated. HTTP/streaming implementations
are maintained separately. This intentionally targets Robotomail's schema subset;
unrepresentable non-null unions stop generation instead of silently losing types.
"""
import argparse
import copy
import hashlib
import json
import re
import subprocess
from pathlib import Path


def snake(name):
    name = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name.replace("-", "_"))
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name).lower()


def pascal(name):
    return "".join(x[:1].upper() + x[1:] for x in re.split(r"[_\- ]", name))


class Contract:
    def __init__(self, spec):
        self.spec = spec
        self.models = {}
        for name, schema in spec["components"]["schemas"].items():
            self.models[self.name(name)] = self.normalize(schema)
        self.ops = []
        for path, item in spec["paths"].items():
            for method, op in item.items():
                if method not in {"get", "post", "patch", "delete", "put"}:
                    continue
                assert op.get("operationId"), (method, path)
                params = {}
                for p in item.get("parameters", []) + op.get("parameters", []):
                    p = self.resolve(p)
                    params[(p["in"], p["name"])] = p
                operation = dict(id=op["operationId"], method=method.upper(), path=path,
                                 summary=op["summary"], description=op["description"],
                                 paths=[p["name"] for p in params.values() if p["in"] == "path"],
                                 params=[p for p in params.values() if p["in"] != "path"],
                                 body=None, upload=False, stream=op["operationId"] == "streamEvents")
                assert set(re.findall(r"\{([^}]+)\}", path)) == set(operation["paths"])
                body = self.resolve(op.get("requestBody", {}))
                if body:
                    content = body["content"]
                    if "multipart/form-data" in content:
                        operation["upload"] = True
                    else:
                        schema = content["application/json"]["schema"]
                        operation["body"] = self.register(schema, pascal(operation["id"]) + "Request")
                success = [self.resolve(r) for code, r in op["responses"].items() if code.startswith("2")]
                response_types = []
                for response in success:
                    content = response.get("content", {})
                    if "application/json" in content:
                        response_types.append(self.register(content["application/json"]["schema"], pascal(operation["id"]) + "Response"))
                assert len(set(response_types)) <= 1, operation["id"]
                operation["response"] = response_types[0] if response_types else None
                if operation["params"]:
                    name = pascal(operation["id"]) + "Params"
                    self.models[name] = self.normalize({"type": "object", "properties": {
                        p["name"]: p["schema"] for p in operation["params"]
                    }, "required": [p["name"] for p in operation["params"] if p.get("required")]})
                    operation["query_type"] = name
                self.ops.append(operation)
        assert len({o["id"] for o in self.ops}) == len(self.ops)
        # Give inline objects stable names, including objects nested in arrays.
        queue = list(self.models)
        for name in queue:
            before = set(self.models)
            self.models[name] = self.name_inline(self.models[name], name, root=True)
            queue.extend(n for n in self.models if n not in before)

    @staticmethod
    def name(name):
        return "ErrorBody" if name == "Error" else name

    def resolve(self, schema):
        if "$ref" in schema:
            assert schema["$ref"].startswith("#/"), "Only local references are supported"
            value = self.spec
            for part in schema["$ref"][2:].split("/"):
                value = value[part]
            return copy.deepcopy(value)
        return copy.deepcopy(schema)

    def normalize(self, schema):
        schema = copy.deepcopy(schema)
        if "$ref" in schema:
            return {"ref": self.name(schema["$ref"].split("/")[-1])}
        if "allOf" in schema:
            merged = {"type": "object", "properties": {}, "required": []}
            for part in schema["allOf"]:
                resolved = self.resolve(part)
                # These branches refine already-declared error fields, not their types.
                if "oneOf" in resolved and all("properties" in b for b in resolved["oneOf"]):
                    continue
                resolved = self.normalize(resolved)
                assert resolved.get("type") == "object", schema
                merged["properties"].update(resolved.get("properties", {}))
                merged["required"].extend(resolved.get("required", []))
            return merged
        union = schema.get("oneOf", schema.get("anyOf"))
        if union:
            nonnull = [p for p in union if p.get("type") != "null"]
            assert len(nonnull) == 1 and len(union) == 2, "Unsupported union: " + str(schema)
            result = self.normalize(nonnull[0])
            result["nullable"] = True
            return result
        typ = schema.get("type")
        if isinstance(typ, list):
            nonnull = [t for t in typ if t != "null"]
            assert len(nonnull) == 1, schema
            typ = nonnull[0]
            schema["nullable"] = True
        if not typ and "enum" in schema:
            typ = "string"
        schema["type"] = typ or "any"
        if "properties" in schema:
            schema["properties"] = {k: self.normalize(v) for k, v in schema["properties"].items()}
        if "items" in schema:
            schema["items"] = self.normalize(schema["items"])
        if isinstance(schema.get("additionalProperties"), dict):
            schema["additionalProperties"] = self.normalize(schema["additionalProperties"])
        return schema

    def register(self, schema, name):
        if "$ref" in schema:
            return self.name(schema["$ref"].split("/")[-1])
        normalized = self.normalize(schema)
        assert name not in self.models or self.models[name] == normalized
        self.models[name] = normalized
        return name

    def name_inline(self, schema, name, root=False):
        if schema.get("type") == "object" and schema.get("properties"):
            if not root:
                self.models[name] = schema
                return {"ref": name, "nullable": schema.get("nullable", False)}
            schema["properties"] = {k: self.name_inline(v, name + pascal(k)) for k, v in schema["properties"].items()}
        if schema.get("type") == "array":
            schema["items"] = self.name_inline(schema["items"], name + "Item")
        return schema

    def typ(self, s, lang):
        t = s.get("type")
        if "ref" in s:
            result = s["ref"]
        elif t == "array":
            item = self.typ(s["items"], lang)
            result = {"node": f"Array<{item}>", "python": f"List[{item}]", "go": f"[]{item}", "rust": f"Vec<{item}>", "ruby": "Array"}[lang]
        elif t == "object":
            val = s.get("additionalProperties")
            value = self.typ(val, lang) if isinstance(val, dict) else {"node": "unknown", "python": "Any", "go": "any", "rust": "serde_json::Value", "ruby": "Object"}[lang]
            result = {"node": f"Record<string, {value}>", "python": f"Dict[str, {value}]", "go": f"map[string]{value}", "rust": f"std::collections::HashMap<String, {value}>", "ruby": "Hash"}[lang]
        elif t == "string" and s.get("enum") and lang in ("node", "python"):
            # Closed value sets become literal unions where the type system can
            # express them without affecting runtime decoding. Go, Rust and Ruby
            # keep a plain string: a strict enum there would fail to decode a
            # value the server adds later.
            values = [json.dumps(v) for v in s["enum"] if v is not None]
            result = " | ".join(values) if lang == "node" else f"Literal[{', '.join(values)}]"
        else:
            result = {
                "node": {"string": "string", "integer": "number", "number": "number", "boolean": "boolean", "any": "unknown", "null": "null"},
                "python": {"string": "str", "integer": "int", "number": "float", "boolean": "bool", "any": "Any", "null": "None"},
                "go": {"string": "string", "integer": "int64", "number": "float64", "boolean": "bool", "any": "any", "null": "any"},
                "rust": {"string": "String", "integer": "i64", "number": "f64", "boolean": "bool", "any": "serde_json::Value", "null": "serde_json::Value"},
                "ruby": {"string": "String", "integer": "Integer", "number": "Float", "boolean": "bool", "any": "Object", "null": "nil"},
            }[lang][t]
        if s.get("nullable"):
            result = {"node": f"{result} | null", "python": f"Optional[{result}]", "go": f"*{result}", "rust": f"Option<{result}>", "ruby": f"{result}?"}[lang]
        return result

    def models_code(self, lang):
        out = {"node": ["// Generated by scripts/generate.py. Do not edit."],
               "python": ['"""Generated API types. Request/response keys use the wire names."""', "from __future__ import annotations", "from typing import Any, Dict, List, Literal, Optional", "from typing_extensions import TypedDict, Required, NotRequired"],
               "go": ["// Code generated by scripts/generate.py. DO NOT EDIT.", "package robotomail"],
               "rust": ["// Generated by scripts/generate.py. Do not edit.", "use serde::{Deserialize, Serialize};"],
               "ruby": ["# Generated by scripts/generate.py. Do not edit.", "module Robotomail"]}[lang]
        for name, schema in self.models.items():
            props = schema.get("properties")
            if lang == "ruby":
                continue
            if not props:
                typ = self.typ(schema, lang)
                out.append({"node": f"export type {name} = {typ};", "python": f"{name} = {typ}", "go": f"type {name} {typ}", "rust": f"pub type {name} = {typ};"}[lang])
                continue
            required = set(schema.get("required", []))
            out.append({"node": f"export interface {name} {{", "python": f"class {name}(TypedDict):", "go": f"type {name} struct {{", "rust": f"#[derive(Debug, Clone, Default, Serialize, Deserialize)]\npub struct {name} {{"}[lang])
            for key, prop in props.items():
                typ = self.typ(prop, lang)
                optional = key not in required
                if lang == "node":
                    out.append(f"  {json.dumps(key)}{'?' if optional else ''}: {typ};")
                elif lang == "python":
                    # Functional TypedDict is needed only for header names with hyphens.
                    if not key.isidentifier():
                        break
                    out.append(f"    {key}: {'NotRequired' if optional else 'Required'}[{typ}]")
                elif lang == "go":
                    out.append(f'    {pascal(key)} {"*" if optional else ""}{typ} `json:"{key}{",omitempty" if optional else ""}"`')
                elif lang == "rust":
                    field = snake(key)
                    if field in {"type", "ref", "match", "loop", "self"}:
                        field = "r#" + field
                    out.append(f'    #[serde(rename = "{key}"{", default, skip_serializing_if = \"Option::is_none\"" if optional else ""})]')
                    out.append(f"    pub {field}: {'Option<' + typ + '>' if optional else typ},")
            if lang == "python" and any(not k.isidentifier() for k in props):
                # Replace the class (no methods) with functional syntax.
                while out and out[-1] != f"class {name}(TypedDict):":
                    out.pop()
                out.pop()
                fields = ", ".join(f'{json.dumps(k)}: {"NotRequired" if k not in required else "Required"}[{self.typ(v, lang)}]' for k, v in props.items())
                out.append(f'{name} = TypedDict("{name}", {{{fields}}})')
            elif lang != "python":
                out.append("}")
            out.append("")
        if lang == "ruby":
            out.extend(["  # Responses are ordinary Hash objects with JSON string keys.", "end"])
        return "\n".join(out).rstrip() + "\n"

    def operations_code(self, lang):
        if lang == "node":
            out = ['// Generated by scripts/generate.py. Do not edit.', 'import * as M from "./models.js";', 'import { Transport, type RequestOptions, type Upload, type EventFrame } from "./transport.js";', 'export class Robotomail extends Transport {']
        elif lang == "python":
            out = ['"""Generated operation bindings."""', 'from __future__ import annotations', 'from typing import Optional, Iterator, AsyncIterator', 'from . import models as M', 'from .transport import SyncTransport, AsyncTransport, Upload, EventFrame', 'class Robotomail(SyncTransport):']
        elif lang == "go":
            out = ['// Code generated by scripts/generate.py. DO NOT EDIT.', 'package robotomail', 'import ("context"; "net/url")']
        elif lang == "rust":
            out = ['// Generated by scripts/generate.py. Do not edit.', 'use crate::{Client, Error, Upload, EventStream, models::*};', 'impl Client {']
        else:
            out = ['# Generated by scripts/generate.py. Do not edit.', 'require_relative "transport"', 'module Robotomail', '  class Client < Transport']
        blocks = []
        for op in self.ops:
            name = op["id"]
            body, qt, result = op["body"], op.get("query_type"), op["response"]
            paths = op["paths"]
            params = op["params"]
            path = op["path"]
            if lang == "node":
                args = [f"{p}: string" for p in paths]
                if body: args.append(f"body: M.{body}")
                if op["upload"]: args.append("file: Upload")
                if qt: args.append(f"params: M.{qt}" + (" = {}" if not any(p.get("required") for p in params) else ""))
                args.append("options: RequestOptions = {}")
                url = '`' + re.sub(r"\{([^}]+)\}", r"${this.segment(\1)}", path) + '`'
                call = f'{json.dumps(op["method"])}, {url}, ' + ("body" if body else "undefined") + ', ' + ("params" if qt else "undefined") + ', options' + (', file' if op["upload"] else '')
                if op["stream"]:
                    line = f'  {name}({", ".join(args)}): AsyncGenerator<EventFrame> {{ return this.stream(params, options); }}'
                else:
                    line = f'  {name}({", ".join(args)}): Promise<M.{result}> {{ return this.request<M.{result}>({call}); }}'
                out.extend([f'  /** {op["summary"]} */', line])
            elif lang == "python":
                args = ["self"] + [f"{snake(p)}: str" for p in paths]
                if body: args.append(f"body: M.{body}")
                if op["upload"]: args.append("file: Upload")
                if qt: args.append(f"params: Optional[M.{qt}] = None")
                url = 'f"' + re.sub(r"\{([^}]+)\}", lambda m: '{self._segment(' + snake(m[1]) + ')}', path) + '"'
                call = f'{json.dumps(op["method"])}, {url}, body=' + ("body" if body else "None") + ', params=' + ("params" if qt else "None") + (', file=file' if op["upload"] else '')
                if op["stream"]:
                    block = [f'    def {snake(name)}({", ".join(args)}) -> Iterator[EventFrame]:', f'        """{op["summary"]}. Close the iterator when stopping early."""', '        return self._stream(params)']
                else:
                    block = [f'    def {snake(name)}({", ".join(args)}) -> M.{result}:', f'        """{op["summary"]}."""', f'        return self._request({call})']
                out.extend(block + [""])
                if op["stream"]:
                    blocks.extend([block[0].replace('Iterator[', 'AsyncIterator['), block[1], block[2], ""])
                else:
                    blocks.extend([block[0].replace('    def ', '    async def '), block[1], block[2].replace('return self.', 'return await self.'), ""])
            elif lang == "go":
                args = ['ctx context.Context'] + [f'{p} string' for p in paths]
                if body: args.append(f'body {body}')
                if op["upload"]: args.append('file Upload')
                if qt: args.append(f'params *{qt}')
                url = json.dumps(path)
                for p in paths:
                    url = url.replace('{' + p + '}', '" + escapeSegment(' + p + ') + "')
                out.append(f'// {pascal(name)} {op["summary"]}.')
                ret = '*EventStream' if op["stream"] else '*' + result
                out.append(f'func (c *Client) {pascal(name)}({", ".join(args)}) ({ret}, error) {{')
                out.extend([f'    if err := validateSegment({p}); err != nil {{ return nil, err }}' for p in paths])
                out.append('    query := url.Values{}')
                out.append('    headers := map[string]string{}')
                if qt:
                    out.append('    if params != nil {')
                    for p in params:
                        field = pascal(p['name'])
                        target = 'headers' if p['in'] == 'header' else 'query'
                        value = f'params.{field}'
                        optional = not p.get('required')
                        if optional: out.append(f'        if {value} != nil {{')
                        value = ('*' if optional else '') + value
                        statement = f'headers[{json.dumps(p["name"])}] = {value}' if target == 'headers' else f'query.Set({json.dumps(p["name"])}, queryValue({value}))'
                        out.append('        ' + statement)
                        if optional: out.append('        }')
                    out.append('    }')
                if op['stream']:
                    out.append('    return c.openStream(ctx, query, headers)')
                else:
                    out.extend([f'    var result {result}', f'    err := c.request(ctx, {json.dumps(op["method"])}, {url}, query, headers, {"body" if body else "nil"}, {"&file" if op["upload"] else "nil"}, &result)', '    if err != nil { return nil, err }', '    return &result, nil'])
                out.append('}')
            elif lang == 'rust':
                args = ['&self'] + [f'{snake(p)}: &str' for p in paths]
                if body: args.append(f'body: &{body}')
                if op['upload']: args.append('file: Upload')
                if qt: args.append(f'params: &{qt}')
                out.append(f'    /// {op["summary"]}.')
                out.append(f'    pub async fn {snake(name)}({", ".join(args)}) -> Result<{"EventStream" if op["stream"] else result}, Error> {{')
                url = 'format!(' + json.dumps(re.sub(r'\{[^}]+\}', '{}', path)) + ''.join(', crate::segment(' + snake(p) + ')?' for p in paths) + ')'
                if not paths: url = json.dumps(path) + '.to_string()'
                out.append(f'        let path = {url};')
                out.append('        let query: Vec<(&str, String)> = vec![];' if not params else '        let mut query: Vec<(&str, String)> = vec![];')
                out.append('        let headers: Vec<(&str, String)> = vec![];' if not any(p['in'] == 'header' for p in params) else '        let mut headers: Vec<(&str, String)> = vec![];')
                for p in params:
                    field = 'params.' + snake(p['name'])
                    target = 'headers' if p['in'] == 'header' else 'query'
                    if p.get('required'):
                        out.append(f'        {target}.push(({json.dumps(p["name"])}, {field}.to_string()));')
                    else:
                        out.append(f'        if let Some(value) = &{field} {{ {target}.push(({json.dumps(p["name"])}, value.to_string())); }}')
                if op['stream']:
                    out.append('        self.open_stream(&path, &query, &headers).await')
                else:
                    out.append(f'        self.request({json.dumps(op["method"])}, &path, &query, &headers, {"Some(serde_json::to_value(body)?)" if body else "None"}, {"Some(file)" if op["upload"] else "None"}).await')
                out.append('    }')
            else:
                args = [snake(p) for p in paths]
                if body: args.append('body')
                if op['upload']: args.append('file')
                if qt: args.append('params: {}')
                url = '"' + re.sub(r'\{([^}]+)\}', lambda m: '#{segment(' + snake(m[1]) + ')}', path) + '"'
                out.append(f'    # {op["summary"]}.')
                out.append(f'    def {snake(name)}({", ".join(args)})')
                if op['stream']:
                    out.append('      stream(params)')
                else:
                    out.append(f'      request({json.dumps(op["method"])}, {url}, body: {"body" if body else "nil"}, params: {"params" if qt else "{}"}, file: {"file" if op["upload"] else "nil"})')
                out.append('    end')
        if lang in {'node', 'rust'}: out.append('}')
        if lang == 'python': out.extend(['class AsyncRobotomail(AsyncTransport):'] + blocks)
        if lang == 'ruby': out.extend(['  end', 'end'])
        return '\n'.join(out).rstrip() + '\n'

    def outputs(self, lang):
        files = {'node': ('src/models.ts', 'src/client.ts'), 'python': ('src/robotomail/models.py', 'src/robotomail/client.py'), 'go': ('models.go', 'operations.go'), 'ruby': ('lib/robotomail/models.rb', 'lib/robotomail/client.rb'), 'rust': ('src/models.rs', 'src/operations.rs')}
        modelpath, clientpath = files[lang]
        api = ['# API reference', '', 'Generated from `openapi.json`. Request and response fields are described in that contract.', '', '| Method | HTTP | Description |', '| --- | --- | --- |']
        for op in self.ops:
            name = op['id'] if lang == 'node' else pascal(op['id']) if lang == 'go' else snake(op['id'])
            api.append(f'| `{name}` | `{op["method"]} {op["path"]}` | {op["summary"]} |')
        models, operations = self.models_code(lang), self.operations_code(lang)
        if lang in {'go', 'rust'}:
            command = ['gofmt'] if lang == 'go' else ['rustfmt', '--edition', '2021', '--emit', 'stdout']
            models = subprocess.run(command, input=models, text=True, capture_output=True, check=True).stdout
            operations = subprocess.run(command, input=operations, text=True, capture_output=True, check=True).stdout
        return {modelpath: models, clientpath: operations, 'API.md': '\n'.join(api) + '\n'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    config = json.loads((args.root / 'sdk.json').read_text())
    raw = (args.root / 'openapi.json').read_bytes()
    contract = Contract(json.loads(raw))
    outputs = contract.outputs(config['language'])
    outputs['contract.json'] = json.dumps({'sha256': hashlib.sha256(raw).hexdigest(), 'operations': [{'id': o['id'], 'method': o['method'], 'path': o['path']} for o in contract.ops]}, indent=2) + '\n'
    stale = []
    for name, content in outputs.items():
        path = args.root / name
        if args.check:
            if not path.exists() or path.read_text() != content: stale.append(name)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
    if stale: raise SystemExit('Stale generated files: ' + ', '.join(stale))
    print(f'{config["language"]}: {len(contract.ops)} operations, {len(contract.models)} models; ' + ('verified' if args.check else 'generated'))


if __name__ == '__main__':
    main()
