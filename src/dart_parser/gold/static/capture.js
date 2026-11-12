(function () {
  var node = document.getElementById("capture-data");
  var host = document.getElementById("filing");
  var bar = document.getElementById("confirm");
  if (!node || !host || !bar) return;
  var data = JSON.parse(node.textContent || "{}");
  var root = host.attachShadow({mode: "open"});
  root.innerHTML = "<style>::selection{background:#e7b008}</style>" + (data.filingHtml || "");
  var pending = null;
  var previewToken = 0;

  root.addEventListener("click", function (event) {
    var target = event.target;
    if (target && target.tagName === "A") event.preventDefault();
  });
  root.addEventListener("pointerup", function () {
    var form = selectedRow();
    if (!form) {
      showRejection("켜진 칸이 없다");
      return;
    }
    var text = selectedText(root);
    if (!text.replace(/\s/g, "")) {
      showRejection("드래그 글자가 비어 있다");
      return;
    }
    var body = new URLSearchParams();
    body.set("token", form.token.value);
    body.set("bundle", form.bundle.value);
    body.set("subject", form.subject.value);
    body.set("text", text);
    var requestToken = ++previewToken;
    fetch(data.previewUrl, {
      method: "POST",
      headers: {"Content-Type": "application/x-www-form-urlencoded"},
      body: body
    }).then(function (response) {
      return response.text().then(function (raw) {
        if (requestToken !== previewToken) return;
        var payload = null;
        try {
          payload = JSON.parse(raw);
        } catch (error) {
          payload = null;
        }
        if (!response.ok || !payload || typeof payload !== "object") {
          showRejection(previewFailureReason(payload, raw));
          return;
        }
        pending = {form: form, text: text, payload: payload};
        renderBar(text, payload);
      });
    });
  });

  document.getElementById("confirm-save").addEventListener("click", function () {
    if (!pending) return;
    var value = readConfirmed(pending.payload);
    if (value === undefined) {
      showReason("값을 고르세요.");
      return;
    }
    var body = new URLSearchParams();
    body.set("token", pending.form.token.value);
    body.set("bundle", pending.form.bundle.value);
    body.set("subject", pending.form.subject.value);
    body.set("text", pending.text);
    body.set("confirmed", JSON.stringify(value));
    fetch(data.captureUrl, {
      method: "POST",
      headers: {"Content-Type": "application/x-www-form-urlencoded"},
      body: body
    }).then(function (response) {
      if (response.redirected || response.ok) {
        window.location.assign(response.url);
        return;
      }
      response.text().then(function (raw) {
        showReason(raw);
        bar.hidden = false;
      });
    });
  });
  document.getElementById("confirm-cancel").addEventListener("click", hideBar);

  document.addEventListener("change", function (event) {
    var input = event.target;
    var form = input && input.form;
    if (!form || !form.classList.contains("capture-row")) return;
    if (input.name !== "row" || !input.checked) return;
    var forms = document.querySelectorAll("form.capture-row");
    for (var i = 0; i < forms.length; i++) {
      if (forms[i] !== form && forms[i].row) forms[i].row.checked = false;
    }
    hideBar();
  });

  document.getElementById("sections").addEventListener("click", function (event) {
    var button = event.target.closest("button[data-section]");
    if (!button) return;
    var name = button.getAttribute("data-section");
    var sections = document.querySelectorAll("section[data-section]");
    var rails = document.querySelectorAll("#sections button");
    for (var i = 0; i < sections.length; i++) {
      if (sections[i].getAttribute("data-section") === name) sections[i].setAttribute("data-active", "1");
      else sections[i].removeAttribute("data-active");
    }
    for (var j = 0; j < rails.length; j++) {
      rails[j].setAttribute("aria-pressed", rails[j] === button ? "true" : "false");
    }
    var forms = document.querySelectorAll("form.capture-row");
    for (var k = 0; k < forms.length; k++) {
      if (forms[k].row) forms[k].row.checked = false;
    }
    hideBar();
    if (name === "표지") {
      host.scrollTop = 0;
      return;
    }
    var phrases = (data.sections && data.sections[name]) || [];
    var headings = root.querySelectorAll("h1,h2,h3,h4,p,th,td");
    for (var p = 0; p < phrases.length; p++) {
      for (var h = 0; h < headings.length; h++) {
        var compact = (headings[h].textContent || "").replace(/\s/g, "");
        if (compact.indexOf(phrases[p]) === 0) {
          headings[h].scrollIntoView();
          return;
        }
      }
    }
  });

  function selectedRow() {
    var forms = document.querySelectorAll("form.capture-row");
    for (var i = 0; i < forms.length; i++) {
      if (forms[i].row && forms[i].row.checked) return forms[i];
    }
    return null;
  }
  function selectedText(shadow) {
    var selection = shadow.getSelection ? shadow.getSelection() : null;
    if (!selection || selection.isCollapsed) return "";
    return selection.toString();
  }
  function renderBar(text, payload) {
    document.getElementById("confirm-evidence").textContent = text;
    var slot = document.getElementById("confirm-control");
    slot.replaceChildren();
    showReason(payload.blocked || "");
    if (payload.blocked) {
      bar.hidden = false;
      return;
    }
    slot.appendChild(controlFor(payload));
    bar.hidden = false;
  }
  function controlFor(payload) {
    if (payload.kind === "enum") {
      var select = document.createElement("select");
      var blank = document.createElement("option");
      blank.value = "";
      select.appendChild(blank);
      (payload.options || []).forEach(function (item) {
        var option = document.createElement("option");
        option.value = item.value;
        option.textContent = item.label;
        if (String(payload.proposal) === item.value || (item.value === "true" && payload.proposal === true) || (item.value === "false" && payload.proposal === false)) {
          option.selected = true;
        }
        select.appendChild(option);
      });
      return select;
    }
    if (payload.kind === "period") {
      var wrap = document.createElement("div");
      wrap.appendChild(labeledInput("start", payload.proposal && payload.proposal.start));
      wrap.appendChild(labeledInput("end", payload.proposal && payload.proposal.end));
      return wrap;
    }
    if (payload.kind === "round") {
      var round = document.createElement("div");
      round.appendChild(labeledInput("raw", payload.proposal && payload.proposal.raw));
      round.appendChild(labeledInput("date", payload.proposal && payload.proposal.date));
      return round;
    }
    var input = document.createElement("input");
    if (payload.kind === "amount") input.value = payload.proposal ? payload.proposal.value : "";
    else if (payload.kind === "number") input.value = payload.proposal == null ? "" : String(payload.proposal);
    else input.value = payload.proposal == null ? "" : String(payload.proposal);
    return input;
  }
  function labeledInput(name, value) {
    var input = document.createElement("input");
    input.name = name;
    input.value = value || "";
    return input;
  }
  function readConfirmed(payload) {
    var slot = document.getElementById("confirm-control");
    if (payload.blocked) return undefined;
    if (payload.kind === "enum") {
      var chosen = slot.querySelector("select").value;
      if (!chosen) return undefined;
      if (chosen === "true") return true;
      if (chosen === "false") return false;
      if (payload.options.length && (payload.options[0].value === "1" || payload.options[0].value === "0")) {
        return Number(chosen);
      }
      return chosen;
    }
    if (payload.kind === "period") {
      var start = slot.querySelector('input[name="start"]').value;
      var end = slot.querySelector('input[name="end"]').value;
      if (!start || !end) return undefined;
      return {start: start, end: end};
    }
    if (payload.kind === "round") {
      var raw = slot.querySelector('input[name="raw"]').value;
      var date = slot.querySelector('input[name="date"]').value;
      if (!raw.trim()) return undefined;
      return date ? {raw: raw, date: date} : {raw: raw};
    }
    var field = slot.querySelector("input");
    if (!field || field.value.trim() === "") return undefined;
    if (payload.kind === "amount" || payload.kind === "number") {
        var number = Number(field.value);
        if (number !== number) return undefined;
        return number;
      }
    return field.value;
  }
  function previewFailureReason(payload, raw) {
    if (payload && payload.error) return payload.error;
    if (raw === "재입수 중" || raw === "재입수가 끝났습니다") return raw;
    return "읽을 수 없습니다.";
  }
  function showRejection(reason) {
    previewToken += 1;
    pending = null;
    showReason(reason);
    bar.hidden = false;
  }
  function showReason(text) {
    document.getElementById("confirm-reason").textContent = text || "";
  }
  function hideBar() {
    previewToken += 1;
    pending = null;
    bar.hidden = true;
  }
})();
