import { expect, type Page } from '@playwright/test';

export async function waitForAppReady(page: Page) {
  await page.goto('/', { waitUntil: 'domcontentloaded' });

  try {
    await expect(page.locator('[data-testid="stApp"]')).toHaveCount(1, { timeout: 30_000 });
    await expect(page.locator('[data-testid="stMain"]')).toHaveCount(1, { timeout: 30_000 });
    await expect(page.locator('[data-fm-ai-e2e-ready="true"]')).toHaveCount(1, {
      timeout: 120_000,
    });
    await expect(page.locator('[data-testid="stSkeleton"]')).toHaveCount(0, { timeout: 120_000 });
    await expect(page.locator('[data-testid="stException"]')).toHaveCount(0);
    await expect(page.locator('body')).not.toContainText('Traceback');
  } catch (error) {
    const diagnostics = await page.evaluate(() => ({
      title: document.title,
      href: location.href,
      body: document.body.innerText.slice(0, 2_000),
      testIds: Array.from(document.querySelectorAll('[data-testid]'))
        .slice(0, 50)
        .map(element => element.getAttribute('data-testid')),
      counts: Object.fromEntries(
        ['stApp', 'stMain', 'stMainBlockContainer', 'stTabs', 'stSkeleton', 'stException'].map(
          testId => [testId, document.querySelectorAll(`[data-testid="${testId}"]`).length],
        ),
      ),
      readyMarker: document.querySelectorAll('[data-fm-ai-e2e-ready="true"]').length,
    }));
    throw new Error(`Aplicação Streamlit não ficou pronta: ${JSON.stringify(diagnostics)}`, {
      cause: error,
    });
  }
}

export async function openTab(page: Page, name: string | RegExp) {
  await expect(page.locator('[data-testid="stSkeleton"]')).toHaveCount(0, { timeout: 30_000 });
  const pattern = typeof name === 'string' ? new RegExp(name) : name;
  const roleTab = page.getByRole('tab', { name: pattern }).first();
  if (await roleTab.count()) {
    await roleTab.click();
    await expect(roleTab).toHaveAttribute('aria-selected', 'true', { timeout: 15_000 });
  } else {
    const textTab = page.getByText(pattern).first();
    if (!(await textTab.count())) {
      const candidates = await page.locator('button, [role="tab"], [data-testid="stTab"]').allTextContents();
      throw new Error(`Aba não encontrada: ${pattern}. Candidatas: ${candidates.join(' | ')}`);
    }
    await textTab.click();
    await expect(textTab).toBeVisible({ timeout: 15_000 });
  }
  await expect(page.locator('[data-testid="stSkeleton"]')).toHaveCount(0, { timeout: 30_000 });
}

export async function expectNoFatal(page: Page) {
  await expect(page.locator('body')).not.toContainText('Traceback');
  await expect(page.locator('body')).not.toContainText('GEMINI_API_KEY');
}

export async function clickAndWaitForStreamlitRerun(page: Page, buttonName: string | RegExp) {
  await expect(page.locator('[data-testid="stSkeleton"]')).toHaveCount(0, { timeout: 30_000 });
  const readyMarker = page.locator('[data-fm-ai-e2e-ready="true"]');
  const button =
    typeof buttonName === 'string'
      ? page.getByRole('button', { name: buttonName, exact: true })
      : page.getByRole('button', { name: buttonName });
  await expect(button).toBeVisible();
  await expect(button).toBeEnabled();

  const runBeforeClick = await readyMarker.getAttribute('data-fm-ai-e2e-run');

  // Streamlit/React pode substituir o nó do botão durante o callback. Disparar o
  // click nativo evita que a automação fique presa ao nó antigo; o contrato real
  // continua sendo o rerun concluído e a pós-condição de cada cenário.
  await button.evaluate((element: HTMLButtonElement) => element.click());

  await expect
    .poll(
      async () => {
        const runAfterClick = await readyMarker.getAttribute('data-fm-ai-e2e-run');
        return runAfterClick !== null && runAfterClick !== runBeforeClick;
      },
      {
        message: `Streamlit deve concluir o rerun após clicar em ${buttonName}`,
        timeout: 30_000,
      },
    )
    .toBe(true);
  await expect(page.locator('[data-testid="stSkeleton"]')).toHaveCount(0, { timeout: 30_000 });
  await expect(page.locator('[data-testid="stException"]')).toHaveCount(0);
}

export async function fillNumber(page: Page, label: string | RegExp, value: string) {
  const expectedValue = Number(value);
  if (value.trim() === '' || !Number.isFinite(expectedValue)) {
    throw new Error(`Valor numérico esperado inválido: ${JSON.stringify(value)}`);
  }

  const input = page.getByRole('spinbutton', { name: label }).first();
  try {
    await expect(page.locator('[data-testid="stSkeleton"]')).toHaveCount(0, { timeout: 30_000 });
    await expect(input).toBeVisible();
    await expect(input).toBeEnabled();

    const atual = Number(await input.inputValue());
    if (Number.isFinite(atual) && Math.abs(atual - expectedValue) < 0.000001) {
      await expect(input).toBeEnabled();
      return;
    }

    const readyMarker = page.locator('[data-fm-ai-e2e-ready="true"]');
    const runBeforeFill = await readyMarker.getAttribute('data-fm-ai-e2e-run');

    // NumberInput é controlado pelo Streamlit/React e pode substituir o nó no
    // primeiro evento de input. Use o setter nativo e valide o rerun completo,
    // depois readquira o locator para provar o valor efetivamente aplicado.
    await input.evaluate((element: HTMLInputElement, nextValue: string) => {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
      if (!setter) throw new Error('setter_nativo_number_input_indisponivel');
      setter.call(element, nextValue);
      element.dispatchEvent(new Event('input', { bubbles: true }));
      element.dispatchEvent(new Event('change', { bubbles: true }));
      element.blur();
    }, value);

    await expect
      .poll(
        async () => {
          const runAfterFill = await readyMarker.getAttribute('data-fm-ai-e2e-run');
          return runAfterFill !== null && runAfterFill !== runBeforeFill;
        },
        {
          message: `Streamlit deve concluir o rerun após preencher ${String(label)}`,
          timeout: 30_000,
        },
      )
      .toBe(true);

    await expect(page.locator('[data-testid="stSkeleton"]')).toHaveCount(0, { timeout: 30_000 });
    await expect(page.locator('[data-testid="stException"]')).toHaveCount(0);

    const refreshedInput = page.getByRole('spinbutton', { name: label }).first();
    await expect(refreshedInput).toBeVisible();
    await expect(refreshedInput).toBeEnabled();
    await expect
      .poll(
        async () => {
          const receivedText = await refreshedInput.inputValue();
          const receivedValue = Number(receivedText);
          if (receivedText.trim() === '' || !Number.isFinite(receivedValue)) {
            throw new Error(`Valor numérico recebido inválido: ${JSON.stringify(receivedText)}`);
          }
          return receivedValue;
        },
        { message: `Campo numérico deve ter o valor ${value}` },
      )
      .toBeCloseTo(expectedValue, 2);
  } catch (error) {
    if (page.isClosed()) {
      throw error;
    }
    let diagnostics;
    try {
      diagnostics = await page.evaluate(() => {
        const accessibleName = (element: Element) =>
          element.getAttribute('aria-label') ??
          element.getAttribute('placeholder') ??
          document.querySelector(`label[for="${element.id}"]`)?.textContent?.trim() ??
          '';
        return {
          spinbuttons: Array.from(document.querySelectorAll('[role="spinbutton"], input[type="number"]'))
            .filter(element => (element as HTMLElement).offsetParent !== null)
            .map(element => ({ name: accessibleName(element), value: (element as HTMLInputElement).value })),
          comboboxes: Array.from(document.querySelectorAll('[role="combobox"]'))
            .filter(element => (element as HTMLElement).offsetParent !== null)
            .map(element => ({
              name: accessibleName(element),
              value: (element as HTMLInputElement).value,
              expanded: element.getAttribute('aria-expanded'),
            })),
          body: document.body.innerText.slice(0, 2_000),
          skeletons: document.querySelectorAll('[data-testid="stSkeleton"]').length,
          exceptions: document.querySelectorAll('[data-testid="stException"]').length,
        };
      });
    } catch {
      throw error;
    }
    throw new Error(`Campo numérico não ficou pronto: ${JSON.stringify(diagnostics)}`, {
      cause: error,
    });
  }
}

export async function selectComboboxOption(
  page: Page,
  label: string | RegExp,
  option: string | RegExp,
) {
  const combobox = page.getByRole('combobox', { name: label }).first();
  const readyMarker = page.locator('[data-fm-ai-e2e-ready="true"]');
  await expect(combobox).toBeVisible();
  await expect(combobox).toBeEnabled();
  if (typeof option === 'string' && (await combobox.inputValue()) === option) {
    await expect(combobox).toHaveValue(option);
    await expect(page.locator('[data-testid="stSkeleton"]')).toHaveCount(0, { timeout: 30_000 });
    return;
  }

  const runBeforeSelection = await readyMarker.getAttribute('data-fm-ai-e2e-run');
  await expect(async () => {
    if (typeof option === 'string' && (await combobox.inputValue()) === option) {
      return;
    }

    await combobox.focus();
    if ((await combobox.getAttribute('aria-expanded')) !== 'true') {
      await combobox.press('ArrowDown');
    }
    await expect(combobox).toHaveAttribute('aria-expanded', 'true', { timeout: 3_000 });

    const listbox = page.getByRole('listbox').filter({ visible: true }).last();
    await expect(listbox).toBeVisible({ timeout: 3_000 });
    const selectedOption = listbox.getByRole('option', {
      name: option,
      exact: typeof option === 'string',
    });
    await expect(selectedOption).toBeVisible({ timeout: 3_000 });
    await selectedOption.click();
  }).toPass({ timeout: 20_000, intervals: [250, 500, 1_000] });

  await expect
    .poll(
      async () => {
        const runAfterSelection = await readyMarker.getAttribute('data-fm-ai-e2e-run');
        return runAfterSelection !== null && runAfterSelection !== runBeforeSelection;
      },
      {
        message: `Streamlit deve concluir o rerun após selecionar ${option}`,
        timeout: 30_000,
      },
    )
    .toBe(true);
  await expect(combobox).toHaveValue(option);
  await expect(combobox).toHaveAttribute('aria-expanded', 'false');
  await expect(page.locator('[data-testid="stSkeleton"]')).toHaveCount(0, { timeout: 30_000 });
  await expect(page.locator('[data-testid="stException"]')).toHaveCount(0);
}
