/**
 * Klientkod för de breda tabellerna (Signaler, Kurs mot vinst): sortering på kolumnrubrik,
 * full fönsterbredd och skuggor vid kanterna när tabellen går att rulla i sidled.
 *
 * Markup: <th data-type="num|text" aria-sort="none|ascending|descending"><button>, celler med
 * data-v (sorteringsvärde, tomt = saknas), första kolumnen = bolagsnamn (lika värden ordnas
 * efter det). Ytterbehållaren har data-table-outer och den rullande data-table-wrap.
 */
import { compareValues } from "./signals";

export function setupSortable(root: HTMLElement, onSort?: () => void): void {
  const tbody = root.querySelector("tbody")!;
  const rows = Array.from(tbody.querySelectorAll<HTMLTableRowElement>("tr"));
  const headers = Array.from(root.querySelectorAll<HTMLTableCellElement>("thead th"));
  headers.forEach((th, col) => {
    th.querySelector("button")?.addEventListener("click", () => {
      // Första klicket: text stigande, tal fallande (störst först).
      const current = th.getAttribute("aria-sort");
      const ascending = current === "none" ? th.dataset.type === "text" : current === "descending";
      headers.forEach((h) => h.setAttribute("aria-sort", "none"));
      th.setAttribute("aria-sort", ascending ? "ascending" : "descending");
      const value = (r: HTMLTableRowElement) => {
        const raw = (r.children[col] as HTMLElement).dataset.v ?? "";
        if (raw === "") return null;
        return th.dataset.type === "num" ? Number(raw) : raw;
      };
      // Lika värden ordnas efter bolagsnamn, så att ordningen alltid blir densamma.
      const name = (r: HTMLTableRowElement) => (r.children[0] as HTMLElement).dataset.v ?? "";
      rows.sort((a, b) => compareValues(value(a), value(b), ascending) || compareValues(name(a), name(b), true));
      tbody.append(...rows);
      onSort?.();
    });
  });
}

export function setupFullWidth(root: HTMLElement): void {
  const outer = root.querySelector<HTMLElement>("[data-table-outer]");
  const wrap = root.querySelector<HTMLElement>("[data-table-wrap]");
  if (!outer || !wrap) return;
  // Full fönsterbredd: CSS:en räknar med 100vw minus rullningslistens bredd (--sbw).
  const setScrollbarWidth = () =>
    document.documentElement.style.setProperty("--sbw", `${window.innerWidth - document.documentElement.clientWidth}px`);
  const updateShadows = () => {
    const max = wrap.scrollWidth - wrap.clientWidth;
    outer.classList.toggle("more-right", max > 1 && wrap.scrollLeft < max - 1);
    outer.classList.toggle("more-left", wrap.scrollLeft > 1);
  };
  wrap.addEventListener("scroll", updateShadows, { passive: true });
  window.addEventListener("resize", () => {
    setScrollbarWidth();
    updateShadows();
  });
  // Fliken kan vara dold när sidan laddas; mät om när tabellen får sin storlek.
  new ResizeObserver(updateShadows).observe(wrap);
  new ResizeObserver(updateShadows).observe(wrap.querySelector("table")!);
  setScrollbarWidth();
  updateShadows();
}
