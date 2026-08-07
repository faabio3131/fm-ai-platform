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
  const readyMarker = page.locator('[data-fm-ai-e2e-ready="true"]');
  const runBeforeClick = await readyMarker.getAttribute('data-fm-ai-e2e-run');
  await page.getByRole('button', { name: buttonName }).click();
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
}

export async function fillNumber(page: Page, label: string | RegExp, value: string) {
  const input = page.getByRole('spinbutton', { name: label }).first();
  try {
    await expect(input).toBeVisible();
    await expect(input).toBeEnabled();
    await input.fill(value);
    await page.keyboard.press('Tab');
    const expectedValue = Number(value);
    if (value.trim() === '' || !Number.isFinite(expectedValue)) {
      throw new Error(`Valor numérico esperado inválido: ${JSON.stringify(value)}`);
    }
    await expect
      .poll(
        async () => {
          const receivedText = await input.inputValue();
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

  const listbox = page.getByRole('listbox').filter({ visible: true }).last();
  await expect(async () => {
    await combobox.focus();
    await combobox.press('ArrowDown');
    await expect(combobox).toHaveAttribute('aria-expanded', 'true', { timeout: 5_000 });
    await expect(listbox).toBeVisible({ timeout: 5_000 });
  }).toPass({ timeout: 15_000 });
  const selectedOption = listbox.getByRole('option', {
    name: option,
    exact: typeof option === 'string',
  });
  await expect(selectedOption).toBeVisible();
  const runBeforeSelection = await readyMarker.getAttribute('data-fm-ai-e2e-run');
  await selectedOption.click();

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
