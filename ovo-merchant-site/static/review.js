// Review screen: submit one group at a time. Each group posts
// its own decision to /api/decide. A group that is never
// submitted approves nothing.
(function () {
  var form = document.getElementById("review-form");
  if (!form) return;
  var runKey = form.getAttribute("data-run-key");
  form.addEventListener("click", function (event) {
    if (event.target.tagName !== "BUTTON") return;
    event.preventDefault();
    var card = event.target.closest(".card");
    if (!card) return;
    var band = card.getAttribute("data-band");
    var chosen = [];
    card.querySelectorAll('input[type="checkbox"]:checked').forEach(function (box) {
      var parts = box.value.split(":");
      chosen.push({ product_id: Number(parts[0]), field: parts.slice(1).join(":") });
    });
    var body = { run_key: runKey,
                 session_token: sessionStorage.getItem("ovo_session_token"),
                 groups: [{ band: band, submitted: true }] };
    if (band === "95_plus") {
      body.groups[0].rejections = chosen;
    } else {
      body.groups[0].approvals = chosen;
    }
    var button = event.target;
    button.disabled = true;
    fetch("/api/decide", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then(function (resp) { return resp.json(); })
      .then(function (data) {
        var div = document.createElement("div");
        if (data.record) {
          div.className = "result";
          div.textContent = "Group " + band + " recorded. Status: " + data.record.status +
            ". Approved rows: " + data.record.publishable_count + ".";
        } else {
          div.className = "result error";
          div.textContent = "Not recorded: " + (data.errors || []).join("; ");
          button.disabled = false;
        }
        card.appendChild(div);
      })
      .catch(function (err) {
        button.disabled = false;
        var div = document.createElement("div");
        div.className = "result error";
        div.textContent = "Not recorded: " + err.message;
        card.appendChild(div);
      });
  });
})();
