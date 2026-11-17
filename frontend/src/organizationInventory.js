// Presentation only: callers supply the server-authorized inventory unchanged.
// These helpers never grant authority or mutate customer records.
export function organizationPage(rows, { query = "", status = "all", page = 0, pageSize = 25 } = {}) {
  const needle = query.trim().toLowerCase();
  const items = rows.filter((row) =>
    (status === "all" || (status === "active" ? row.active === true : row.active === false)) &&
    (!needle || [row.name, row.code, row.id].join(" ").toLowerCase().includes(needle)),
  );
  const lastPage = Math.max(0, Math.ceil(items.length / pageSize) - 1);
  const currentPage = Math.min(Math.max(0, page), lastPage);
  return {
    items,
    visible: items.slice(currentPage * pageSize, (currentPage + 1) * pageSize),
    page: currentPage,
    total: items.length,
    start: items.length ? currentPage * pageSize + 1 : 0,
    end: Math.min((currentPage + 1) * pageSize, items.length),
  };
}

export function organizationPageFor(rows, id, pageSize = 25) {
  const index = rows.findIndex((row) => row.id === id);
  return Math.floor(Math.max(0, index) / pageSize);
}
