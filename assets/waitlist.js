/* promptdecode · the waitlist page (waitlist.html) only.

   This file is deliberately separate from assets/promptdecode.js. The decoder
   page promises that nothing pasted into it leaves the browser, and its own
   script may not contain a network call (tools/check.py). This page is the one
   place that talks to the network, and only to the waitlist Worker.

   Posts { email, product: "promptdecode", captchaToken } to
   https://api.promptdeco.de/v1/waitlist, the Cratefield harness waitlist
   module (PromptDecode/waitlist-backend), the same contract as the Shoal,
   release.show and Colonizer waitlists. captchaToken is a Cloudflare Turnstile
   token (managed widget, action "waitlist"); the Worker binds it to the apex
   hostname promptdeco.de and refuses a join without one (400, problem type
   ending /captcha-failed). A valid join answers 202 whether or not the
   address was already on the list. */
(function () {
  "use strict";

  var root = document.documentElement;
  root.classList.remove("no-js");
  try {
    var stored = localStorage.getItem("pd-theme");
    if (stored === "light" || stored === "dark") root.dataset.theme = stored;
  } catch (e) { /* private mode */ }

  var API = "https://api.promptdeco.de/v1/waitlist";
  var SITEKEY = "0x4AAAAAAFRBPFEFkqpL7FjD";
  var TURNSTILE = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit&onload=pdTurnstileReady";

  var form = document.getElementById("wl-form");
  if (!form) return;
  var email = document.getElementById("wl-email");
  var button = document.getElementById("wl-go");
  var human = document.getElementById("wl-human");
  var msg = document.getElementById("wl-msg");
  var label = button.textContent;
  var widget = null;
  var token = "";
  var broken = false;

  function say(text, bad) {
    msg.textContent = text;
    msg.classList.toggle("wl__msg--bad", !!bad);
  }

  function unavailable() {
    broken = true;
    say("The human check did not load, so nothing can be sent right now. Try again later.", true);
  }

  function theme() {
    var t = root.dataset.theme;
    if (t === "light" || t === "dark") return t;
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
  }

  function render() {
    if (!window.turnstile || !human) return;
    if (widget !== null) { window.turnstile.remove(widget); widget = null; }
    human.hidden = false;
    widget = window.turnstile.render(human, {
      sitekey: SITEKEY,
      action: "waitlist",
      theme: theme(),
      callback: function (t) { token = t; },
      "expired-callback": function () { token = ""; },
      "error-callback": function () { token = ""; }
    });
  }

  function reset() {
    token = "";
    if (window.turnstile && widget !== null) window.turnstile.reset(widget);
  }

  window.pdTurnstileReady = function () { clearTimeout(waited); render(); };
  var tag = document.createElement("script");
  tag.src = TURNSTILE; tag.async = true; tag.defer = true;
  tag.onerror = unavailable;
  document.head.appendChild(tag);
  var waited = setTimeout(function () { if (!window.turnstile) unavailable(); }, 10000);

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var value = email.value.trim();
    if (!value || !email.checkValidity()) {
      say("That does not look like an email address.", true);
      email.focus();
      return;
    }
    if (broken || !window.turnstile) { unavailable(); return; }
    if (!token) { say("Complete the human check first.", true); return; }

    button.disabled = true;
    button.textContent = "Sending…";
    say("");
    var body = { email: value, product: "promptdecode", captchaToken: token };
    fetch(API, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
      .then(function (res) {
        if (res.ok) return;
        return res.json().catch(function () { return {}; }).then(function (p) {
          var type = (p && p.type) || "";
          if (/\/captcha-failed$/.test(type)) throw new Error("captcha");
          if (res.status === 429) throw new Error("rate");
          if (res.status === 400) throw new Error("invalid");
          throw new Error(String(res.status));
        });
      })
      .then(function () {
        form.reset();
        if (human) human.hidden = true;
        say("Check your inbox for a confirmation link. Your place is held once you open it.");
      })
      .catch(function (err) {
        var why = err && err.message;
        say(why === "captcha" ? "The human check failed. Try it again."
          : why === "rate" ? "Too many tries. Wait a minute and try again."
          : why === "invalid" ? "That address was not accepted. Check it and try again."
          : "Could not reach the waitlist right now. Try again in a while.", true);
        reset();
      })
      .then(function () { button.disabled = false; button.textContent = label; });
  });
})();
