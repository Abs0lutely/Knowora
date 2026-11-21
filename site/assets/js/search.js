(() => {
  const input = document.querySelector("#search-input");
  const list = document.querySelector("#search-results");
  const count = document.querySelector("#search-count");
  if (!input || !list || !count) return;

  let records = [];
  const normalize = (value) => String(value || "").toLocaleLowerCase();
  input.value = new URLSearchParams(window.location.search).get("q") || "";
  const render = () => {
    const query = normalize(input.value.trim());
    const matches = query
      ? records.filter((item) => normalize([item.title, item.course, item.chapter, ...(item.tags || [])].join(" ")).includes(query))
      : [];
    count.textContent = query ? `找到 ${matches.length} 篇文档` : "输入关键词开始搜索。";
    list.replaceChildren();
    for (const item of matches) {
      const row = document.createElement("li");
      const link = document.createElement("a");
      link.href = new URL(item.url, new URL(window.KNOWORA_SEARCH_INDEX, window.location.href)).href;
      link.textContent = item.title;
      const details = document.createElement("small");
      details.textContent = [item.course, item.chapter, ...(item.tags || [])].join(" · ");
      row.append(link, details);
      list.append(row);
    }
  };

  fetch(window.KNOWORA_SEARCH_INDEX)
    .then((response) => {
      if (!response.ok) throw new Error("Search index unavailable");
      return response.json();
    })
    .then((data) => {
      records = Array.isArray(data) ? data : [];
      render();
    })
    .catch(() => {
      count.textContent = "搜索目录暂时无法加载，请稍后重试。";
    });
  input.addEventListener("input", render);
})();
