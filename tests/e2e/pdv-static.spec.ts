import { expect, test } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

test.describe('PDV visual and monetary safeguards', () => {
  test('keeps cliente balcão as a real option and identifies cash input currency', () => {
    const appSource = readFileSync(join(process.cwd(), 'app.py'), 'utf-8');
    const pdvUtilsSource = readFileSync(join(process.cwd(), 'pdv_utils.py'), 'utf-8');

    expect(appSource).not.toContain('Choose an option');
    expect(appSource).toContain('key="pdv_cliente_id"');
    expect(appSource).not.toContain('key="pdv_cliente"');
    expect(appSource).toContain('st.markdown("Valor recebido do cliente")');
    expect(appSource).toContain('st.markdown("### R$")');
    expect(appSource).toContain('valor_recebido_pdv = st.number_input(');
    expect(pdvUtilsSource).toContain('CLIENTE_BALCAO_LABEL = "Cliente Balcão / Não Identificado"');
  });
});
