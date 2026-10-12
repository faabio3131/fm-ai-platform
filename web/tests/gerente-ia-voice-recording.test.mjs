import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(
  new URL("../src/features/gerente-ia/components/GerenteIAWorkspace.tsx", import.meta.url),
  "utf8",
);

test("Gerente IA mostra feedback de captação e usa analyser real durante gravação", () => {
  assert.match(source, /createMediaStreamSource/);
  assert.match(source, /createAnalyser\(\)/);
  assert.match(source, /getByteFrequencyData/);
  assert.match(source, /Gravando voz/);
  assert.match(source, /Nível do áudio captado pelo microfone/);
  assert.match(source, /formatarDuracaoVoz/);
  assert.match(source, /gravador\.start\(250\)/);
});

test("Gerente IA preserva revisão humana antes de enviar a pergunta transcrita", () => {
  assert.match(source, /transcreverGerenteIA\(blob\)/);
  assert.match(source, /setPergunta\(texto\)/);
  assert.match(source, /type="submit"/);
  assert.doesNotMatch(source, /transcreverGerenteIA\(blob\).*perguntarGerenteIA/s);
});
