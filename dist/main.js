// Minimal status check for the (normally hidden) Tauri window.
// CSP allows connect-src to 127.0.0.1:4100 only.
(function poll() {
  fetch("http://127.0.0.1:4100/health")
    .then(function (r) { return r.json(); })
    .then(function (h) {
      document.getElementById("status").innerHTML =
        'Proxy <span class="ok">running</span> — v' + h.version +
        " · " + h.total_requests_tracked.toLocaleString() + " requests tracked";
    })
    .catch(function () {
      document.getElementById("status").textContent =
        "Proxy not reachable on 127.0.0.1:4100";
    })
    .finally(function () { setTimeout(poll, 10000); });
})();
