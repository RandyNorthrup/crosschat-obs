// Loads files of the extension the way the browser does: one after the other in one global scope (here, this test
// process's), and hands back that scope.
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

export const extensionSource = (file) => readFileSync(new URL('../../extension/' + file, import.meta.url), 'utf8');

export function loadExtension(...files) {
  files.forEach((file) => vm.runInThisContext(extensionSource(file), { filename: file }));
  return globalThis;
}
