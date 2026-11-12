(function () {
  var node = document.getElementById("capture-data");
  var host = document.getElementById("filing");
  var bar = document.getElementById("confirm");
  if (!node || !host || !bar) return;
  var data = JSON.parse(node.textContent || "{}");
  var root = host.attachShadow({mode: "open"});
  root.innerHTML = "<style>"
    + "::selection{background:#e7b008}"
    + ".gold-snap{outline:1px dashed #243028;outline-offset:-1px}"
    + ".gold-source{background:#f3d56a}"
    + "</style>"
    + (data.filingHtml || "");
  var pending = null;
  var picked = null;
  var previewToken = 0;
  var armedPointer = false;
  var pickerOpenedAt = 0;
  var hoverEl = null;
  var lastLocatorKey = "";
  var autoKey = "gold-auto-advance";
  var storedAuto = sessionStorage.getItem(autoKey);
  var autoOn = storedAuto === null ? true : storedAuto === "1";
  var mapKey = "gold-field-map:" + (data.docId || "") + ":" + (data.pass || data.base || "");
  var undoKey = "gold-undo:" + (data.docId || "") + ":" + (data.pass || data.base || "");
  var locatorMap = readJson(mapKey, {});
  var undoStack = readJson(undoKey, []);
  if (!Array.isArray(undoStack)) undoStack = [];
  var undoBusy = false;
  var storedSplit = sessionStorage.getItem("gold-split");
  if (storedSplit && /^\d{1,2}%$/.test(storedSplit)) {
    document.documentElement.style.setProperty("--split", storedSplit);
  }
  restoreOpenSection();

  function restoreOpenSection() {
    var stored = sessionStorage.getItem("gold-open-section");
    if (stored === null) return;
    sessionStorage.removeItem("gold-open-section");
    if (!stored) return;
    var sections = document.querySelectorAll("section[data-section]");
    var match = null;
    for (var i = 0; i < sections.length; i++) {
      if (sections[i].getAttribute("data-section") === stored) match = sections[i];
    }
    if (!match) return;
    for (var j = 0; j < sections.length; j++) {
      if (sections[j] === match) sections[j].setAttribute("data-active", "1");
      else sections[j].removeAttribute("data-active");
    }
    var rails = document.querySelectorAll("#sections button");
    for (var k = 0; k < rails.length; k++) {
      var pressed = rails[k].getAttribute("data-section") === stored;
      rails[k].setAttribute("aria-pressed", pressed ? "true" : "false");
    }
  }

  root.addEventListener("click", function (event) {
    var target = event.target;
    if (target && target.tagName === "A") event.preventDefault();
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
  root.addEventListener("pointerover", function (event) {
    var target = event.target;
    var el = target && target.closest ? target.closest("td, th, p") : null;
    if (el && !root.contains(el)) el = null;
    if (hoverEl === el) return;
    if (hoverEl) hoverEl.classList.remove("gold-snap");
    hoverEl = el;
    if (hoverEl) hoverEl.classList.add("gold-snap");
  });
  document.addEventListener("pointerdown", function (event) {
    armedPointer = pathHasFiling(event);
  });
  document.addEventListener("pointerup", function (event) {
    var inside = pathHasFiling(event);
    var startedInside = armedPointer;
    armedPointer = false;
    if (!inside && !startedInside) return;
    var selection = root.getSelection ? root.getSelection() : null;
    var collapsed = !selection || selection.isCollapsed || !selectedText(root);
    var text = "";
    var method = "text_drag";
    var block = null;
    var range = null;
    if (!collapsed) {
      text = normalizeText(selection.toString());
      method = "text_drag";
      block = blockOf(selection.anchorNode);
      if (selection.rangeCount) range = selection.getRangeAt(0).cloneRange();
    } else if (inside) {
      var target = pathTarget(event);
      block = target && target.closest ? target.closest("td, th, p") : null;
      if (!block || !root.contains(block)) {
        showRejection("드래그 글자가 비어 있다");
        return;
      }
      text = normalizeText(block.textContent || "");
      method = "cell_click";
    } else {
      return;
    }
    if (!text) {
      showRejection("드래그 글자가 비어 있다");
      return;
    }
    var locator = locatorFor(block, text, method);
    var form = selectedRow();
    if (!form) {
      openPicker(event, text, method, locator, range);
      return;
    }
    beginLoad(form, text, method, locator, range);
  });

  function beginLoad(form, text, method, locator, range) {
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
        if (!response.ok) {
          showRejection(previewFailureReason(payload, raw));
          return;
        }
        if (!payload || typeof payload !== "object") {
          showRejection(previewFailureReason(payload, raw));
          return;
        }
        var proposed = proposalConfirmed(payload);
        if (payload.blocked || proposed === undefined) {
          pending = {
            form: form,
            text: text,
            payload: payload,
            method: method,
            locator: locator,
            range: range
          };
          renderBar(text, payload);
          return;
        }
        postCapture(form, text, proposed, method, locator, redirectAfterCapture, range, false);
      });
    });
  }

  document.getElementById("confirm-save").addEventListener("click", function () {
    if (!pending) return;
    if (amountNeedsUnit(pending.payload)) {
      showReason("단위를 먼저 선택하세요");
      pointAtUnit(pending.form);
      return;
    }
    var value = readConfirmed(pending.payload);
    if (value === undefined) {
      showReason("값을 고르세요.");
      return;
    }
    var method = pending.method || "text_drag";
    if (!sameJson(value, proposalConfirmed(pending.payload))) method = "manual_edit";
    postCapture(
      pending.form,
      pending.text,
      value,
      method,
      pending.locator,
      redirectAfterCapture,
      pending.range,
      false
    );
  });
  function redirectAfterCapture(response) {
    var landed = response.url || "";
    if (landed.indexOf("miss_bundle=") !== -1 || landed.indexOf("miss_subject=") !== -1) {
      showReason("읽을 수 없습니다.");
      bar.hidden = false;
      return;
    }
    if (response.redirected || response.ok) {
      var open = document.querySelector("section[data-section][data-active]");
      if (open) {
        sessionStorage.setItem("gold-open-section", open.getAttribute("data-section") || "");
      }
      window.location.assign(response.url);
      return;
    }
    response.text().then(function (raw) {
      showReason(raw);
      bar.hidden = false;
    });
  }
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
    showSection(name);
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

  document.addEventListener("pointerover", function (event) {
    var form = event.target && event.target.closest
      ? event.target.closest("form.capture-row")
      : null;
    if (form) scrollToLocator(form);
  });
  document.addEventListener("focusin", function (event) {
    var form = event.target && event.target.closest
      ? event.target.closest("form.capture-row")
      : null;
    if (form) scrollToLocator(form);
  });
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") hidePicker();
    var undo = (event.ctrlKey || event.metaKey) && (event.key === "z" || event.key === "Z");
    if (!undo || event.shiftKey) return;
    if (editingText(event.target)) return;
    event.preventDefault();
    undoLast();
  });
  document.addEventListener("submit", function (event) {
    var form = event.target;
    if (!form || !form.classList || !form.classList.contains("capture-row")) return;
    var submitter = event.submitter;
    if (!submitter || submitter.name !== "status" || submitter.value !== "clear") return;
    event.preventDefault();
    postStatus(form, "clear", false);
  });
  document.addEventListener("click", function (event) {
    if (Date.now() - pickerOpenedAt < 400) return;
    var picker = document.getElementById("field-picker");
    if (!picker || picker.hidden) return;
    if (picker.contains(event.target)) return;
    hidePicker();
  });
  var exportLink = document.getElementById("export-json");
  if (exportLink) {
    exportLink.addEventListener("click", function (event) {
      event.preventDefault();
      var name = (data.docId || "gold").replace(/\//g, "-") + ".json";
      fetch(data.exportUrl).then(function (response) {
        if (!response.ok) return null;
        return response.json();
      }).then(function (rows) {
        if (!rows || !Array.isArray(rows)) return;
        for (var i = 0; i < rows.length; i++) {
          var extra = locatorMap[rows[i].field_key];
          if (!extra) continue;
          if (extra.locator) rows[i].locator = extra.locator;
          if (extra.selection_method) rows[i].selection_method = extra.selection_method;
        }
        downloadJson(name, JSON.stringify(rows, null, 2));
      });
    });
  }
  var autoButton = document.getElementById("auto-advance");
  if (autoButton) {
    autoButton.addEventListener("click", function () {
      autoOn = !autoOn;
      sessionStorage.setItem(autoKey, autoOn ? "1" : "0");
      renderAuto();
    });
  }
  renderAuto();
  var resizer = document.getElementById("pane-resizer");
  if (resizer) {
    resizer.addEventListener("pointerdown", function (event) {
      event.preventDefault();
      if (resizer.setPointerCapture) resizer.setPointerCapture(event.pointerId);
      function move(ev) {
        var layout = document.querySelector(".layout");
        if (!layout) return;
        var rect = layout.getBoundingClientRect();
        if (!rect.width) return;
        var min = 12 * 16;
        var x = ev.clientX - rect.left;
        if (x < min) x = min;
        if (x > rect.width - min) x = rect.width - min;
        var pct = Math.round((x / rect.width) * 100);
        if (pct < 20) pct = 20;
        if (pct > 80) pct = 80;
        var value = pct + "%";
        document.documentElement.style.setProperty("--split", value);
        sessionStorage.setItem("gold-split", value);
      }
      function up() {
        resizer.removeEventListener("pointermove", move);
        resizer.removeEventListener("pointerup", up);
      }
      resizer.addEventListener("pointermove", move);
      resizer.addEventListener("pointerup", up);
    });
  }

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
    var saveButton = document.getElementById("confirm-save");
    if (amountNeedsUnit(payload)) {
      if (saveButton) saveButton.disabled = true;
      pointAtUnit(pending && pending.form);
      bar.hidden = false;
      return;
    }
    if (saveButton) saveButton.disabled = false;
    if (payload.blocked) {
      bar.hidden = false;
      return;
    }
    slot.appendChild(controlFor(payload));
    bar.hidden = false;
  }
  function amountNeedsUnit(payload) {
    return !!(
      payload
      && payload.kind === "amount"
      && payload.blocked === "단위를 먼저 선택하세요"
    );
  }
  function pointAtUnit(form) {
    var marked = document.querySelectorAll("select.gold-unit-needed");
    for (var i = 0; i < marked.length; i++) {
      marked[i].classList.remove("gold-unit-needed");
    }
    var section = form && form.closest ? form.closest("section[data-section]") : null;
    var select = section ? section.querySelector('select[name="unit_scale"]') : null;
    if (!select) return;
    select.classList.add("gold-unit-needed");
    if (select.scrollIntoView) select.scrollIntoView({block: "center"});
    if (select.focus) select.focus();
  }
  function editingText(target) {
    if (!target) return false;
    if (target.isContentEditable) return true;
    var tag = target.tagName;
    if (tag === "TEXTAREA" || tag === "SELECT") return true;
    if (tag !== "INPUT") return false;
    var type = String(target.type || "text").toLowerCase();
    return type === "text" || type === "search" || type === "number"
      || type === "password" || type === "email" || type === "url" || type === "tel"
      || type === "date" || type === "time" || type === "datetime-local"
      || type === "month" || type === "week";
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
    if (amountNeedsUnit(payload)) return undefined;
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
  function proposalConfirmed(payload) {
    if (!payload || payload.blocked) return undefined;
    if (payload.kind === "enum") {
      if (payload.proposal === null || payload.proposal === undefined || payload.proposal === "") {
        return undefined;
      }
      var options = payload.options || [];
      var matched = null;
      var count = 0;
      for (var i = 0; i < options.length; i++) {
        var optionValue = options[i].value;
        var hit = String(optionValue) === String(payload.proposal)
          || (optionValue === "true" && payload.proposal === true)
          || (optionValue === "false" && payload.proposal === false);
        if (!hit) continue;
        matched = optionValue;
        count += 1;
      }
      if (count !== 1) return undefined;
      if (matched === "true") return true;
      if (matched === "false") return false;
      if (options.length && (options[0].value === "1" || options[0].value === "0")) {
        return Number(matched);
      }
      return matched;
    }
    if (payload.kind === "period") {
      var period = payload.proposal;
      if (!period || !period.start || !period.end) return undefined;
      return {start: period.start, end: period.end};
    }
    if (payload.kind === "round") {
      var round = payload.proposal;
      if (!round || !String(round.raw || "").trim()) return undefined;
      return round.date ? {raw: String(round.raw), date: String(round.date)} : {raw: String(round.raw)};
    }
    if (payload.kind === "amount") {
      if (!payload.proposal || payload.proposal.value == null || payload.proposal.value === "") {
        return undefined;
      }
      return payload.proposal.value;
    }
    if (payload.proposal == null || payload.proposal === "") return undefined;
    return payload.proposal;
  }
  function postCapture(form, text, value, method, locator, onRedirect, range, skipUndo, onDone) {
    var before = readState(form);
    var body = new URLSearchParams();
    body.set("token", form.token.value);
    body.set("bundle", form.bundle.value);
    body.set("subject", form.subject.value);
    body.set("text", text);
    body.set("confirmed", JSON.stringify(value));
    fetch(data.captureUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json"
      },
      body: body
    }).then(function (response) {
      var type = response.headers.get("Content-Type") || "";
      if (type.indexOf("application/json") !== -1) {
        return response.text().then(function (raw) {
          var payload = null;
          try {
            payload = JSON.parse(raw);
          } catch (error) {
            payload = null;
          }
          if (!response.ok || !payload || payload.ok === false) {
            var reason = (payload && payload.error) || "읽을 수 없습니다.";
            if (onDone) onDone(false, reason);
            else {
              showReason(reason);
              bar.hidden = false;
            }
            return;
          }
          if (!skipUndo) pushUndo(form, before);
          writeState(form, payload);
          rememberLocator(form, locator, method);
          var marked = highlightSource(locator, range, fieldLabel(form));
          if (marked && marked.scrollIntoView) marked.scrollIntoView({block: "center"});
          bar.hidden = true;
          pending = null;
          if (autoOn && !skipUndo) {
            var next = nextEmpty(form);
            if (next) arm(next);
          }
          if (onDone) onDone(true);
        });
      }
      if (onDone) {
        return response.text().then(function (raw) {
          onDone(false, raw || "읽을 수 없습니다.");
        });
      }
      if (onRedirect) onRedirect(response);
    }).catch(function () {
      if (onDone) onDone(false, "읽을 수 없습니다.");
    });
  }
  function postStatus(form, status, skipUndo, onDone) {
    var before = readState(form);
    var body = new URLSearchParams();
    body.set("token", form.token.value);
    body.set("bundle", form.bundle.value);
    body.set("subject", form.subject.value);
    body.set("status", status);
    fetch(form.action, {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json"
      },
      body: body
    }).then(function (response) {
      var type = response.headers.get("Content-Type") || "";
      if (type.indexOf("application/json") === -1) {
        if (onDone) {
          return response.text().then(function (raw) {
            onDone(false, raw || "읽을 수 없습니다.");
          });
        }
        redirectAfterCapture(response);
        return;
      }
      return response.text().then(function (raw) {
        var payload = null;
        try {
          payload = JSON.parse(raw);
        } catch (error) {
          payload = null;
        }
        if (!response.ok || !payload || payload.ok === false) {
          if (onDone) onDone(false, (payload && payload.error) || "읽을 수 없습니다.");
          return;
        }
        if (!skipUndo) pushUndo(form, before);
        writeState(form, payload);
        if (status === "clear") forgetLocator(form);
        if (onDone) onDone(true);
      });
    }).catch(function () {
      if (onDone) onDone(false, "읽을 수 없습니다.");
    });
  }
  function postRemove(form, index, skipUndo, onDone) {
    var before = readState(form);
    var kind = form.bundle.value === "notes_toc" ? "remove_title" : "remove_item";
    var body = new URLSearchParams();
    body.set("token", form.token.value);
    body.set("bundle", form.bundle.value);
    body.set("subject", form.subject.value);
    body.set("status", kind);
    body.set("index", String(index));
    fetch(form.action, {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json"
      },
      body: body
    }).then(function (response) {
      var type = response.headers.get("Content-Type") || "";
      if (type.indexOf("application/json") === -1) {
        if (onDone) {
          return response.text().then(function (raw) {
            onDone(false, raw || "읽을 수 없습니다.");
          });
        }
        redirectAfterCapture(response);
        return;
      }
      return response.text().then(function (raw) {
        var payload = null;
        try {
          payload = JSON.parse(raw);
        } catch (error) {
          payload = null;
        }
        if (!response.ok || !payload || payload.ok === false) {
          if (onDone) onDone(false, (payload && payload.error) || "읽을 수 없습니다.");
          return;
        }
        if (!skipUndo) pushUndo(form, before);
        writeState(form, payload);
        if (onDone) onDone(true);
      });
    }).catch(function () {
      if (onDone) onDone(false, "읽을 수 없습니다.");
    });
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
    var saveButton = document.getElementById("confirm-save");
    if (saveButton) saveButton.disabled = false;
    var marked = document.querySelectorAll("select.gold-unit-needed");
    for (var i = 0; i < marked.length; i++) marked[i].classList.remove("gold-unit-needed");
  }
  function normalizeText(text) {
    if (!text) return "";
    var out = text.normalize ? text.normalize("NFKC") : text;
    out = out.replace(/[\u00a0\u2002\u2003\u2009\u200a\u202f\u205f\u3000\ufeff]/g, " ");
    out = out.replace(/[\u200b\u200c\u200d\u2060]/g, "");
    var parts = out.split(/\s+/);
    var kept = [];
    for (var i = 0; i < parts.length; i++) {
      if (parts[i]) kept.push(parts[i]);
    }
    return kept.join(" ");
  }
  function pathHasFiling(event) {
    var path = event.composedPath ? event.composedPath() : [event.target];
    for (var i = 0; i < path.length; i++) {
      if (path[i] === host || path[i] === root) return true;
    }
    return false;
  }
  function pathTarget(event) {
    var path = event.composedPath ? event.composedPath() : [event.target];
    return path[0];
  }
  function blockOf(node) {
    var el = node && node.nodeType === 1 ? node : (node && node.parentElement);
    while (el) {
      if (el.tagName === "TD" || el.tagName === "TH" || el.tagName === "P") return el;
      el = el.parentElement;
    }
    return node && node.nodeType === 1 ? node : (node && node.parentElement);
  }
  function locatorFor(block, normalized, method) {
    var full = normalizeText(block ? (block.textContent || "") : normalized);
    var start = 0;
    var end = full.length;
    if (method === "text_drag") {
      var at = full.indexOf(normalized);
      if (at >= 0) {
        start = at;
        end = at + normalized.length;
      }
    }
    return {
      css_selector: block ? cssPath(block) : "",
      xpath: block ? xpathOf(block) : "",
      start_offset: start,
      end_offset: end
    };
  }
  function cssPath(element) {
    var parts = [];
    var node = element;
    while (node && node.nodeType === 1) {
      if (node.id && /^[A-Za-z_][A-Za-z0-9_-]*$/.test(node.id)) {
        parts.unshift("#" + node.id);
        break;
      }
      var parent = node.parentElement;
      var tag = node.tagName.toLowerCase();
      if (!parent) {
        parts.unshift(tag);
        break;
      }
      var index = 1;
      var sib = node;
      while ((sib = sib.previousElementSibling)) {
        if (sib.tagName === node.tagName) index += 1;
      }
      parts.unshift(tag + ":nth-of-type(" + index + ")");
      node = parent;
    }
    return parts.join(" > ");
  }
  function xpathOf(element) {
    var parts = [];
    var node = element;
    while (node && node.nodeType === 1) {
      if (node.id && /^[A-Za-z_][A-Za-z0-9_-]*$/.test(node.id)) {
        parts.unshift('//*[@id="' + node.id + '"]');
        break;
      }
      var index = 1;
      var sib = node;
      while ((sib = sib.previousElementSibling)) {
        if (sib.tagName === node.tagName) index += 1;
      }
      parts.unshift(node.tagName.toLowerCase() + "[" + index + "]");
      node = node.parentElement;
    }
    if (parts.length && parts[0].charAt(0) === "/") return parts.join("/");
    return "/" + parts.join("/");
  }
  function queryFiling(selector) {
    if (!selector) return null;
    try {
      return root.querySelector(selector);
    } catch (error) {
      return null;
    }
  }
  function highlightSource(locator, range, label) {
    if (range && !range.collapsed) {
      var span = document.createElement("span");
      span.className = "gold-source";
      if (label) span.title = label;
      try {
        range.surroundContents(span);
        return span;
      } catch (error) {
        if (span.parentNode) span.parentNode.removeChild(span);
      }
    }
    if (!locator || !locator.css_selector) return null;
    var el = queryFiling(locator.css_selector);
    if (!el) return null;
    el.classList.add("gold-source");
    if (label) el.title = label;
    return el;
  }
  function scrollToLocator(form) {
    var key = fieldKey(form);
    if (key === lastLocatorKey) return;
    lastLocatorKey = key;
    var saved = locatorMap[key];
    if (!saved || !saved.locator || !saved.locator.css_selector) return;
    var el = queryFiling(saved.locator.css_selector);
    if (!el || !el.scrollIntoView) return;
    el.classList.add("gold-source");
    if (saved.label) el.title = saved.label;
    el.scrollIntoView({block: "center"});
  }
  function rememberLocator(form, locator, method) {
    if (!locator || !locator.css_selector) return;
    locatorMap[fieldKey(form)] = {
      locator: locator,
      selection_method: method,
      label: fieldLabel(form)
    };
    sessionStorage.setItem(mapKey, JSON.stringify(locatorMap));
  }
  function forgetLocator(form) {
    delete locatorMap[fieldKey(form)];
    sessionStorage.setItem(mapKey, JSON.stringify(locatorMap));
  }
  function restoreLocator(form, before) {
    var key = fieldKey(form);
    if (!before || !before.locator) delete locatorMap[key];
    else {
      locatorMap[key] = {
        locator: before.locator,
        selection_method: before.method || "text_drag",
        label: fieldLabel(form)
      };
    }
    sessionStorage.setItem(mapKey, JSON.stringify(locatorMap));
  }
  function fieldKey(form) {
    return form.bundle.value + "/" + form.subject.value;
  }
  function fieldLabel(form) {
    var label = form.querySelector("label");
    return label ? normalizeText(label.textContent || "") : "";
  }
  function findForm(bundle, subject) {
    var forms = document.querySelectorAll("form.capture-row");
    for (var i = 0; i < forms.length; i++) {
      if (forms[i].bundle.value === bundle && forms[i].subject.value === subject) return forms[i];
    }
    return null;
  }
  function readState(form) {
    if (!form.hasAttribute("data-filled")) return null;
    var replay = null;
    var raw = form.getAttribute("data-replay");
    if (raw) {
      try {
        replay = JSON.parse(raw);
      } catch (error) {
        replay = null;
      }
    }
    var saved = locatorMap[fieldKey(form)];
    return {
      status: form.getAttribute("data-status") || "",
      evidence: form.getAttribute("data-evidence") || "",
      replay: replay,
      shown: savedText(form),
      lines: readLines(form),
      entries: readEntries(form),
      locator: saved ? saved.locator : null,
      method: saved ? saved.selection_method : null
    };
  }
  function readEntries(form) {
    var raw = form.getAttribute("data-value");
    if (!raw) return null;
    var parsed = null;
    try {
      parsed = JSON.parse(raw);
    } catch (error) {
      return null;
    }
    if (form.bundle.value === "notes_toc" && parsed && Array.isArray(parsed.titles)) {
      return parsed.titles.map(function (title) { return String(title); });
    }
    if (form.bundle.value === "communications" && Array.isArray(parsed)) {
      var entries = [];
      for (var i = 0; i < parsed.length; i++) {
        var item = parsed[i];
        if (!item || typeof item !== "object") continue;
        var entry = {raw: String(item.raw || "")};
        if (item.date) entry.date = String(item.date);
        entries.push(entry);
      }
      return entries;
    }
    return null;
  }
  function writeState(form, payload) {
    var progress = document.getElementById("doc-progress");
    if (progress && payload.recorded != null && payload.row_total != null) {
      progress.textContent = "기록 " + payload.recorded + "/" + payload.row_total;
    }
    if (payload.cleared || !payload.status) {
      form.removeAttribute("data-filled");
      form.removeAttribute("data-status");
      form.removeAttribute("data-evidence");
      form.removeAttribute("data-replay");
      form.removeAttribute("data-value");
      setSavedValue(form, "");
      clearLines(form);
      return;
    }
    form.setAttribute("data-filled", "1");
    form.setAttribute("data-status", payload.status);
    form.setAttribute("data-evidence", payload.evidence || "");
    if (payload.replay === null || payload.replay === undefined) form.removeAttribute("data-replay");
    else form.setAttribute("data-replay", JSON.stringify(payload.replay));
    if (isListField(form)) {
      if (payload.value === null || payload.value === undefined) form.removeAttribute("data-value");
      else form.setAttribute("data-value", JSON.stringify(payload.value));
    }
    setSavedValue(form, payload.shown || "");
    if (payload.lines) renderLines(form, payload.lines);
    else clearLines(form);
  }
  function setSavedValue(form, shown) {
    var paragraph = form.querySelector(".saved-value");
    if (!paragraph) return;
    paragraph.replaceChildren();
    var lines = String(shown || "").split("\n");
    for (var i = 0; i < lines.length; i++) {
      if (i) paragraph.appendChild(document.createElement("br"));
      if (lines[i]) paragraph.appendChild(document.createTextNode(lines[i]));
    }
  }
  function savedText(form) {
    var paragraph = form.querySelector(".saved-value");
    return paragraph ? paragraph.textContent || "" : "";
  }
  function readLines(form) {
    var box = form.nextElementSibling;
    if (!box || !box.classList || !box.classList.contains("saved-lines")) return null;
    var spans = box.querySelectorAll("span");
    var lines = [];
    for (var i = 0; i < spans.length; i++) lines.push(spans[i].textContent || "");
    return lines;
  }
  function clearLines(form) {
    var box = form.nextElementSibling;
    if (!box || !box.classList || !box.classList.contains("saved-lines")) return;
    box.replaceChildren();
  }
  function renderLines(form, lines) {
    var box = form.nextElementSibling;
    if (!box || !box.classList || !box.classList.contains("saved-lines")) {
      box = document.createElement("div");
      box.className = "saved-lines";
      form.insertAdjacentElement("afterend", box);
    }
    box.replaceChildren();
    var kind = form.bundle.value === "notes_toc" ? "remove_title" : "remove_item";
    for (var i = 0; i < lines.length; i++) {
      var row = document.createElement("form");
      row.method = "post";
      row.action = form.action;
      row.appendChild(hiddenInput("token", form.token.value));
      row.appendChild(hiddenInput("bundle", form.bundle.value));
      row.appendChild(hiddenInput("subject", form.subject.value));
      row.appendChild(hiddenInput("index", String(i)));
      var span = document.createElement("span");
      span.textContent = lines[i];
      row.appendChild(span);
      var button = document.createElement("button");
      button.type = "submit";
      button.name = "status";
      button.value = kind;
      button.textContent = "지우기";
      row.appendChild(button);
      box.appendChild(row);
    }
  }
  function hiddenInput(name, value) {
    var input = document.createElement("input");
    input.type = "hidden";
    input.name = name;
    input.value = value;
    return input;
  }
  function pushUndo(form, before) {
    undoStack.push({
      bundle: form.bundle.value,
      subject: form.subject.value,
      before: before
    });
    sessionStorage.setItem(undoKey, JSON.stringify(undoStack));
  }
  function undoLast() {
    if (undoBusy || !undoStack.length) return;
    var entry = undoStack[undoStack.length - 1];
    var form = findForm(entry.bundle, entry.subject);
    if (!form) return;
    undoBusy = true;
    applyUndo(form, entry.before, function (ok, reason) {
      undoBusy = false;
      if (!ok) {
        showReason(reason || "읽을 수 없습니다.");
        bar.hidden = false;
        return;
      }
      restoreLocator(form, entry.before);
      commitUndo();
    });
  }
  function applyUndo(form, before, done) {
    if (!before) {
      postStatus(form, "clear", true, done);
      return;
    }
    if (before.status === "not_applicable" || before.status === "not_in_regime") {
      postStatus(form, before.status, true, done);
      return;
    }
    if (isListField(form) && before.status === "found") {
      restoreList(form, before, done);
      return;
    }
    if (before.status === "found" && before.replay !== null && before.replay !== undefined) {
      postCapture(
        form,
        before.evidence || "",
        before.replay,
        before.method || "manual_edit",
        before.locator || null,
        null,
        null,
        true,
        done
      );
      return;
    }
    postStatus(form, "clear", true, done);
  }
  function isListField(form) {
    return (form.bundle.value === "notes_toc" && form.subject.value === "value")
      || (form.bundle.value === "communications" && form.subject.value === "items");
  }
  function restoreList(form, before, done) {
    var current = readLines(form) || [];
    var previous = before.lines || [];
    if (current.length === previous.length + 1 && listPrefix(previous, current)) {
      postRemove(form, current.length - 1, true, done);
      return;
    }
    replayList(form, before, done);
  }
  function listPrefix(previous, current) {
    for (var i = 0; i < previous.length; i++) {
      if (current[i] !== previous[i]) return false;
    }
    return true;
  }
  function replayList(form, before, done) {
    var current = readLines(form) || [];
    var steps = before.entries && before.entries.length ? before.entries : (before.lines || []);
    if (!current.length) {
      replayLines(form, before, steps, 0, done);
      return;
    }
    postStatus(form, "clear", true, function (ok, reason) {
      if (!ok) {
        done(false, reason);
        return;
      }
      replayLines(form, before, steps, 0, done);
    });
  }
  function replayLines(form, before, steps, index, done) {
    if (index >= steps.length) {
      done(true);
      return;
    }
    var step = steps[index];
    postCapture(
      form,
      lineText(form, step),
      lineConfirmed(form, step),
      before.method || "manual_edit",
      before.locator || null,
      null,
      null,
      true,
      function (ok, reason) {
        if (!ok) {
          done(false, reason);
          return;
        }
        replayLines(form, before, steps, index + 1, done);
      }
    );
  }
  function lineText(form, step) {
    if (step && typeof step === "object") return String(step.raw || "");
    var text = String(step || "");
    if (form.bundle.value === "communications") return communicationRaw(text);
    return text;
  }
  function lineConfirmed(form, step) {
    if (step && typeof step === "object") {
      var item = {raw: String(step.raw || "")};
      if (step.date) item.date = String(step.date);
      return item;
    }
    if (form.bundle.value === "communications") return {raw: communicationRaw(step)};
    return String(step || "");
  }
  function communicationRaw(line) {
    var text = String(line || "");
    var space = text.indexOf(" ");
    if (space > 0 && /^\d+$/.test(text.slice(0, space))) return text.slice(space + 1);
    return text;
  }
  function commitUndo() {
    undoStack.pop();
    sessionStorage.setItem(undoKey, JSON.stringify(undoStack));
  }
  function nextEmpty(from) {
    var forms = document.querySelectorAll("form.capture-row");
    var start = 0;
    for (var i = 0; i < forms.length; i++) {
      if (forms[i] === from) start = i + 1;
    }
    for (var j = start; j < forms.length; j++) {
      if (!forms[j].hasAttribute("data-filled")) return forms[j];
    }
    for (var k = 0; k < start; k++) {
      if (!forms[k].hasAttribute("data-filled")) return forms[k];
    }
    return null;
  }
  function arm(form) {
    var section = form.closest("section[data-section]");
    if (section) showSection(section.getAttribute("data-section"));
    var forms = document.querySelectorAll("form.capture-row");
    for (var i = 0; i < forms.length; i++) {
      if (forms[i].row) forms[i].row.checked = forms[i] === form;
    }
    if (form.row && form.row.focus) form.row.focus();
  }
  function showSection(name) {
    var sections = document.querySelectorAll("section[data-section]");
    var rails = document.querySelectorAll("#sections button");
    for (var i = 0; i < sections.length; i++) {
      if (sections[i].getAttribute("data-section") === name) sections[i].setAttribute("data-active", "1");
      else sections[i].removeAttribute("data-active");
    }
    for (var j = 0; j < rails.length; j++) {
      rails[j].setAttribute("aria-pressed", rails[j].getAttribute("data-section") === name ? "true" : "false");
    }
  }
  function openPicker(event, text, method, locator, range) {
    picked = {text: text, method: method, locator: locator, range: range};
    pickerOpenedAt = Date.now();
    var picker = document.getElementById("field-picker");
    if (!picker) return;
    picker.hidden = false;
    picker.style.left = Math.max(8, event.clientX || 8) + "px";
    picker.style.top = Math.max(8, event.clientY || 8) + "px";
    fillPicker(activeSectionName());
  }
  function fillPicker(sectionName) {
    var picker = document.getElementById("field-picker");
    if (!picker) return;
    picker.replaceChildren();
    var title = document.createElement("p");
    title.id = "picker-title";
    title.textContent = "켜진 칸이 없다";
    picker.appendChild(title);
    var fields = document.createElement("div");
    var empty = emptyForms(sectionName);
    for (var i = 0; i < empty.length; i++) {
      fields.appendChild(pickerButton(empty[i]));
    }
    picker.appendChild(fields);
    var sections = document.createElement("div");
    var buttons = document.querySelectorAll("#sections button");
    for (var j = 0; j < buttons.length; j++) {
      var name = buttons[j].getAttribute("data-section");
      if (!name || name === sectionName) continue;
      var jump = document.createElement("button");
      jump.type = "button";
      jump.textContent = name;
      jump.setAttribute("data-picker-section", name);
      jump.addEventListener("click", function (clickEvent) {
        var next = clickEvent.currentTarget.getAttribute("data-picker-section");
        showSection(next);
        fillPicker(next);
      });
      sections.appendChild(jump);
    }
    picker.appendChild(sections);
  }
  function pickerButton(form) {
    var button = document.createElement("button");
    button.type = "button";
    button.textContent = fieldLabel(form);
    button.setAttribute("data-bundle", form.bundle.value);
    button.setAttribute("data-subject", form.subject.value);
    button.addEventListener("click", function () {
      var load = picked;
      hidePicker();
      if (!load) return;
      arm(form);
      beginLoad(form, load.text, load.method, load.locator, load.range);
    });
    return button;
  }
  function emptyForms(sectionName) {
    var sections = document.querySelectorAll("section[data-section]");
    var section = null;
    for (var i = 0; i < sections.length; i++) {
      if (sections[i].getAttribute("data-section") === sectionName) section = sections[i];
    }
    if (!section) return [];
    var forms = section.querySelectorAll("form.capture-row");
    var empty = [];
    for (var j = 0; j < forms.length; j++) {
      if (!forms[j].hasAttribute("data-filled")) empty.push(forms[j]);
    }
    return empty;
  }
  function activeSectionName() {
    var open = document.querySelector("section[data-section][data-active]");
    return open ? (open.getAttribute("data-section") || "") : "";
  }
  function hidePicker() {
    var picker = document.getElementById("field-picker");
    if (picker) picker.hidden = true;
    picked = null;
  }
  function renderAuto() {
    var button = document.getElementById("auto-advance");
    if (!button) return;
    button.setAttribute("aria-pressed", autoOn ? "true" : "false");
    button.textContent = autoOn ? "자동 이동 켜짐" : "자동 이동 꺼짐";
  }
  function readJson(key, fallback) {
    try {
      var parsed = JSON.parse(sessionStorage.getItem(key) || "");
      if (parsed && typeof parsed === "object") return parsed;
    } catch (error) {
      return fallback;
    }
    return fallback;
  }
  function sameJson(left, right) {
    return JSON.stringify(left) === JSON.stringify(right);
  }
  function downloadJson(name, text) {
    var blob = new Blob([text], {type: "application/json"});
    var url = URL.createObjectURL(blob);
    var link = document.createElement("a");
    link.href = url;
    link.download = name;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
  }
})();
