// Reviewed local assets only. No npm/Node runtime is needed by deployed Python app.
import { copyFileSync, mkdirSync, writeFileSync, readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { build } from "esbuild";
const dest = new URL(
  "../../backend/app/static/vendor/console/",
  import.meta.url,
);
mkdirSync(dest, { recursive: true });
const copies = {
  "@xterm/xterm": ["lib/xterm.js", "css/xterm.css", "LICENSE"],
  "@xterm/addon-fit": ["lib/addon-fit.js", "LICENSE"],
  "@xterm/addon-search": ["lib/addon-search.js", "LICENSE"],
  "@noble/hashes": ["LICENSE"],
};
const entries = [];
for (const [name, files] of Object.entries(copies)) {
  for (const file of files) {
    const target =
      file === "LICENSE"
        ? name.replaceAll("/", "-").replace("@", "") + ".LICENSE"
        : file.split("/").pop();
    copyFileSync(
      new URL("node_modules/" + name + "/" + file, import.meta.url),
      new URL(target, dest),
    );
    entries.push(target);
  }
}
await build({
  stdin: {
    contents: "export {sha256} from '@noble/hashes/sha2.js';",
    resolveDir: process.cwd(),
  },
  bundle: true,
  format: "esm",
  platform: "browser",
  target: "es2022",
  minify: true,
  outfile: new URL("hash.js", dest).pathname,
});
entries.push("hash.js");
writeFileSync(
  new URL("PROVENANCE.json", dest),
  JSON.stringify(
    {
      source: "https://registry.npmjs.org",
      packages: JSON.parse(
        readFileSync(new URL("package.json", import.meta.url)),
      ).dependencies,
      sha256: Object.fromEntries(
        entries.map((name) => [
          name,
          createHash("sha256")
            .update(readFileSync(new URL(name, dest)))
            .digest("hex"),
        ]),
      ),
    },
    null,
    2,
  ) + "\n",
);
