import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("four stages, real approvals, duplicate-click prevention, export and themes", async ({
  page,
  request,
}) => {
  const fixture = await request.get("/api/test-fixture").then((r) => r.json());
  await page.goto(`/studio/${fixture.job}/prepare`);
  await expect(
    page.getByRole("heading", { name: "Source interval" }),
  ).toBeVisible();
  await page.getByRole("spinbutton", { name: "Point X · 0–1" }).fill(".42");
  await page.getByRole("button", { name: "Add point", exact: true }).click();
  await expect(page.getByText("Unsaved changes")).toBeVisible();
  await page.reload();
  await expect(page.getByText("Unsaved changes")).toBeVisible();
  // Discard only the browser draft; the original fixture remains approved-reviewable.
  await page.evaluate(
    (id) => localStorage.removeItem(`draft:${id}`),
    fixture.job,
  );
  await page.reload();
  await page.getByRole("link", { name: "Review", exact: true }).click();
  await page.getByText("Compare with original", { exact: true }).click();
  await expect(page.locator(".comparison video")).toHaveCount(2);
  await page
    .getByRole("button", { name: "Approve upload preparation" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Generation route" }),
  ).toBeVisible();
  let posts = 0;
  await page
    .getByRole("combobox", { name: "Finished output plan" })
    .selectOption("original");
  page.on("request", (r) => {
    if (r.method() === "POST" && r.url().endsWith("/previews")) posts++;
  });
  const submit = page.getByRole("button", { name: "Submit 480p preview" });
  await expect(submit).toBeEnabled();
  await expect(page.getByText(/\$NaN/)).toHaveCount(0);
  await submit.dblclick({ force: true });
  await expect(
    page.getByRole("button", { name: "Accept this preview" }),
  ).toBeVisible({ timeout: 15000 });
  expect(posts).toBe(1);
  const job = await request
    .get(`/api/jobs/${fixture.job}`)
    .then((r) => r.json());
  expect(job.attempts).toHaveLength(1);
  expect(job.spent_usd).toBe(0.42);
  await expect(submit).toBeEnabled();
  await submit.click();
  await expect(page.locator(".attempt")).toHaveCount(2);
  await expect(
    page.getByRole("button", { name: "Accept this preview" }),
  ).toBeEnabled({ timeout: 15000 });
  await Promise.all([
    page.waitForResponse(
      (r) =>
        r.url().includes("/approve-preview/") &&
        r.request().method() === "POST",
    ),
    page.getByRole("button", { name: "Accept this preview" }).click(),
  ]);
  const accepted = await request
    .get(`/api/jobs/${fixture.job}`)
    .then((r) => r.json());
  expect(accepted.preview_approval).toBe(accepted.attempts[0].id);
  await expect(
    page.getByRole("heading", { name: "Finalization", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("radio", { name: /Original preview resolution/ })
    .check();
  await page.getByRole("button", { name: "Finalize selected output" }).click();
  await expect(
    page.getByRole("link", { name: /Generation master/ }),
  ).toBeVisible({
    timeout: 20000,
  });
  await expect(page.locator(".viewer-heading")).toContainText("Final delivery");
  await page
    .getByRole("combobox", { name: "View output" })
    .selectOption("preview");
  await expect(page.locator(".viewer-heading")).toContainText("preview");
  for (const theme of ["light", "dark"]) {
    await page
      .getByRole("combobox", { name: "Color theme" })
      .selectOption(theme);
    await page.getByRole("link", { name: "Review", exact: true }).click();
    await page.screenshot({
      path: `../docs/screenshots/studio-${theme}.png`,
      fullPage: true,
    });
    const violations = (await new AxeBuilder({ page }).analyze()).violations;
    expect(
      violations.map((v) => ({
        id: v.id,
        nodes: v.nodes.map((n) => n.target),
      })),
    ).toEqual([]);
    await page.screenshot({
      path: `../docs/screenshots/studio-${theme}.png`,
      fullPage: true,
    });
  }
});

test("responsive inspector, keyboard alternatives and stale revision recovery", async ({
  page,
  request,
}) => {
  const fixture = await request.get("/api/test-fixture").then((r) => r.json());
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/studio/${fixture.job}/prepare`);
  await page.getByRole("button", { name: "Inspector", exact: true }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("spinbutton", { name: "Point X · 0–1" }).fill(".51");
  await page.getByRole("button", { name: "Add point", exact: true }).click();
  await request.post("/api/test-fixture/stale");
  await expect(
    page.getByRole("button", { name: "Load latest revision" }),
  ).toBeVisible({ timeout: 10000 });
  await expect(
    page.getByRole("button", { name: "Save preparation settings" }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Load latest revision" }).click();
  await page.getByRole("button", { name: "Close inspector" }).click();
  await expect(
    page.getByRole("button", { name: "Inspector", exact: true }),
  ).toBeFocused();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  const violations = (await new AxeBuilder({ page }).analyze()).violations;
  expect(violations.map((v) => v.id)).toEqual([]);
});

test("read-only reconnection state", async ({ page }) => {
  await page.route("**/api/events", (route) => route.abort());
  await page.goto("/");
  await expect(page.getByText("Reconnecting", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Projects", exact: true }),
  ).toBeVisible();
});

test("three cast intervals and consent persist; one-generation cap survives reload", async ({
  page,
  request,
}) => {
  const fixture = await request.get("/api/test-fixture").then((r) => r.json());
  await page.goto(`/studio/${fixture.job}/prepare`);
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Subject 3", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Add", exact: true }),
  ).toBeDisabled();
  await page
    .getByRole("combobox", { name: "Reference category" })
    .selectOption("human");
  await page
    .getByLabel("This person consents to this video generation")
    .check();
  await page.getByRole("spinbutton", { name: "Frame", exact: true }).fill("24");
  await page.getByRole("button", { name: "Add tracking interval" }).click();
  await page
    .getByRole("spinbutton", { name: "Interval 1 end frame" })
    .fill("72");
  await page.getByRole("button", { name: "Add point", exact: true }).click();
  await page.getByRole("button", { name: "Save preparation settings" }).click();
  await expect(
    page.locator(".studio-meta").getByText("Revision 2", { exact: true }),
  ).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: "Subject 3", exact: true }).click();
  await expect(
    page.getByRole("spinbutton", { name: "Interval 1 start frame" }),
  ).toHaveValue("24");
  await expect(
    page.getByLabel("This person consents to this video generation"),
  ).toBeChecked();
  const saved = await request
    .get(`/api/jobs/${fixture.job}`)
    .then((r) => r.json());
  expect(saved.approval).toBeNull();
  expect(saved.recipe.subjects[2].annotations[0].frame).toBe(24);

  const single = await request.get("/api/test-fixture").then((r) => r.json());
  await page.goto(`/studio/${single.job}/review`);
  await page
    .getByRole("button", { name: "Approve upload preparation" })
    .click();
  await page
    .getByRole("spinbutton", { name: "Generation submission limit" })
    .fill("1");
  await page.getByRole("button", { name: "Save limit", exact: true }).click();
  await page
    .getByRole("combobox", { name: "Finished output plan" })
    .selectOption("original");
  await page.getByRole("button", { name: "Submit 480p preview" }).click();
  await expect(
    page.getByRole("button", { name: "Accept this preview" }),
  ).toBeEnabled({ timeout: 15000 });
  await page.reload();
  await expect(
    page.getByRole("button", { name: "Submit 480p preview" }),
  ).toBeDisabled();
  const job = await request
    .get(`/api/jobs/${single.job}`)
    .then((r) => r.json());
  expect(job.generation_limit).toBe(1);
  expect(job.attempts).toHaveLength(1);
  const quotes = await request
    .get(`/api/jobs/${single.job}/quotes?finish=original`)
    .then((r) => r.json());
  const repeated = await request.post(`/api/jobs/${single.job}/previews`, {
    data: {
      revision: job.revision,
      quote_id: quotes.find((q: { eligible: boolean }) => q.eligible).id,
      operation_id: "independent-second-operation",
      pilot: true,
    },
  });
  expect(repeated.status()).toBe(409);
});
