(function () {
  const toggle = document.getElementById("reportsSidebarToggle");
  const closeButton = document.getElementById("reportsSidebarClose");
  const sidebar = document.getElementById("reportsSidebar");
  const backdrop = document.getElementById("reportsSidebarBackdrop");
  const accountToggle = document.getElementById("reportsAccountToggle");
  const accountMenu = document.getElementById("reportsAccountMenu");
  const account = document.getElementById("reportsAccount");

  if (!toggle || !closeButton || !sidebar || !backdrop) return;

  function setOpen(open, restoreFocus) {
    sidebar.classList.toggle("open", open);
    toggle.classList.toggle("active", open);
    backdrop.hidden = !open;
    toggle.setAttribute("aria-expanded", String(open));
    toggle.setAttribute("aria-label", open ? "Close Reports navigation" : "Open Reports navigation");
    document.body.classList.toggle("reports-sidebar-open", open);
    if (open) closeButton.focus();
    else if (restoreFocus) toggle.focus();
  }

  toggle.addEventListener("click", function () {
    setOpen(toggle.getAttribute("aria-expanded") !== "true", true);
  });
  closeButton.addEventListener("click", function () {
    setOpen(false, true);
  });
  backdrop.addEventListener("click", function () {
    setOpen(false, true);
  });
  sidebar.querySelectorAll("a").forEach(function (link) {
    link.addEventListener("click", function () {
      if (window.matchMedia("(max-width: 1024px)").matches) setOpen(false, false);
    });
  });
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && toggle.getAttribute("aria-expanded") === "true") {
      setOpen(false, true);
    }
  });
  window.addEventListener("resize", function () {
    if (window.innerWidth > 1024 && toggle.getAttribute("aria-expanded") === "true") {
      setOpen(false, false);
    }
  });

  if (accountToggle && accountMenu && account) {
    accountToggle.addEventListener("click", function () {
      const open = accountToggle.getAttribute("aria-expanded") !== "true";
      accountMenu.hidden = !open;
      accountToggle.setAttribute("aria-expanded", String(open));
    });
    document.addEventListener("click", function (event) {
      if (!account.contains(event.target)) {
        accountMenu.hidden = true;
        accountToggle.setAttribute("aria-expanded", "false");
      }
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && accountToggle.getAttribute("aria-expanded") === "true") {
        accountMenu.hidden = true;
        accountToggle.setAttribute("aria-expanded", "false");
        accountToggle.focus();
      }
    });
  }
})();
