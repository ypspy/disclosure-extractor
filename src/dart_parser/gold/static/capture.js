(function () {
  var node = document.getElementById("capture-data");
  if (!node) return;
  var data = JSON.parse(node.textContent || "{}");
  var host = document.getElementById("filing");
  if (!host) return;
  var root = host.attachShadow({mode: "open"});
  root.innerHTML = data.filingHtml || "";
  root.addEventListener("click", function (event) {
    event.preventDefault();
    var chosen = selectedRow();
    if (!chosen) return;
    var body = new URLSearchParams();
    body.set("token", chosen.token.value);
    body.set("bundle", chosen.bundle.value);
    body.set("subject", chosen.subject.value);
    body.set("text", (event.target && event.target.textContent) || "");
    fetch(data.captureUrl, {
      method: "POST",
      headers: {"Content-Type": "application/x-www-form-urlencoded"},
      body: body
    }).then(function (response) {
      if (!response.ok) {
        return response.text().then(function (text) {
          var slot = chosen.querySelector(".row-error");
          if (slot) slot.textContent = text;
        });
      }
      window.location.assign(response.url);
    });
  });
  root.addEventListener("submit", function (event) {
    event.preventDefault();
  });
  document.addEventListener("click", function (event) {
    var link = event.target && event.target.closest
      ? event.target.closest("a[data-scroll]")
      : null;
    if (!link) return;
    event.preventDefault();
    var target = root.getElementById(link.getAttribute("data-scroll"));
    if (target && target.scrollIntoView) target.scrollIntoView();
  });
  document.addEventListener("change", function (event) {
    if (!event.target || event.target.name !== "row") return;
    var forms = document.querySelectorAll("form.capture-row");
    for (var i = 0; i < forms.length; i++) {
      if (forms[i].row && forms[i].row !== event.target) forms[i].row.checked = false;
    }
  });
  function selectedRow() {
    var forms = document.querySelectorAll("form.capture-row");
    for (var i = 0; i < forms.length; i++) {
      if (forms[i].row && forms[i].row.checked) return forms[i];
    }
    return null;
  }
})();
