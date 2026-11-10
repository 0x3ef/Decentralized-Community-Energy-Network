import fs from "node:fs";
const schema = JSON.parse(
  fs.readFileSync(new URL("./openapi.json", import.meta.url)),
);
function type(s) {
  if (s.$ref) return s.$ref.split("/").at(-1);
  if (s.enum) return s.enum.map((x) => JSON.stringify(x)).join(" | ");
  if (s.anyOf) return s.anyOf.map(type).join(" | ");
  if (s.allOf) return s.allOf.map(type).join(" & ");
  if (s.type === "array") return `Array<${type(s.items)}>`;
  if (s.type === "object" || s.properties) {
    return `{ ${Object.entries(s.properties ?? {})
      .map(
        ([k, v]) =>
          `${JSON.stringify(k)}${s.required?.includes(k) ? "" : "?"}: ${type(v)}`,
      )
      .join(
        "; ",
      )}${s.additionalProperties ? `; [key: string]: ${typeof s.additionalProperties === "object" ? type(s.additionalProperties) : "unknown"}` : ""} }`;
  }
  return (
    {
      string: "string",
      integer: "number",
      number: "number",
      boolean: "boolean",
      null: "null",
    }[s.type] ?? "unknown"
  );
}
fs.writeFileSync(
  new URL("../src/shared/api/generated.ts", import.meta.url),
  "// Generated from the checked-in FastAPI OpenAPI snapshot. npm run generate:api\n" +
    Object.entries(schema.components.schemas)
      .map(([k, v]) => `export type ${k} = ${type(v)}`)
      .join("\n") +
    "\n",
);
