import { cpSync, existsSync, mkdirSync, rmSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const sourceRoot = __dirname;
const outputRoot = path.join(__dirname, "dist");
const copiedEntries = ["index.html", "whitepaper.html", "src"];

rmSync(outputRoot, { recursive: true, force: true });
mkdirSync(outputRoot, { recursive: true });

for (const entry of copiedEntries) {
  const sourcePath = path.join(sourceRoot, entry);
  const outputPath = path.join(outputRoot, entry);

  if (!existsSync(sourcePath)) {
    throw new Error(`Missing UI build input: ${sourcePath}`);
  }

  cpSync(sourcePath, outputPath, { recursive: true });
}

console.log(`Built Maps UI to ${outputRoot}`);
