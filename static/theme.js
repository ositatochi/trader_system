(() => {
  const button = document.getElementById("theme-toggle");
  if (!button) return;

  const updateButton = () => {
    button.textContent = document.documentElement.dataset.theme === "light" ? "☀️" : "🌙";
  };

  updateButton();
  button.addEventListener("click", () => {
    const theme = document.documentElement.dataset.theme === "light" ? "dark" : "light";
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem("trader-theme", theme); } catch (_) {}
    updateButton();
  });
})();