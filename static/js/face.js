/*
 * PawTrack - camera helpers for face login and face registration.
 * The browser only captures frames. The server (InsightFace) does the
 * recognition and stores a face descriptor, never the photo.
 */
(function () {
  "use strict";

  function csrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    if (meta) return meta.content;
    var hidden = document.getElementById("pawCsrf");
    return hidden ? hidden.value : "";
  }

  function setStatus(element, message, kind) {
    if (!element) return;
    element.textContent = message || "";
    element.className = "face-status" + (kind ? " " + kind : "");
  }

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, function (character) {
      return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[character];
    });
  }

  function wait(ms) {
    return new Promise(function (resolve) { setTimeout(resolve, ms); });
  }

  function cameraError(error) {
    if (!error) return "Could not open the camera.";
    if (error.name === "NotAllowedError" || error.name === "SecurityError") {
      return "Camera permission was denied. Allow camera access in the browser and try again.";
    }
    if (error.name === "NotFoundError" || error.name === "DevicesNotFoundError") {
      return "No camera was found on this device.";
    }
    if (error.name === "NotReadableError" || error.name === "TrackStartError") {
      return "The camera is already being used by another app. Close it and try again.";
    }
    return error.message || "Could not open the camera.";
  }

  async function startCamera(video, placeholder) {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      throw new Error("Camera access needs HTTPS or localhost. Open PawTrack using an https:// address.");
    }
    var stream = await navigator.mediaDevices.getUserMedia({
      video: {facingMode: "user", width: {ideal: 640}, height: {ideal: 480}},
      audio: false
    });
    try {
      video.srcObject = stream;
      await video.play();
    } catch (error) {
      stream.getTracks().forEach(function (track) { track.stop(); });
      throw error;
    }
    video.classList.add("live");
    if (placeholder) placeholder.hidden = true;
    return stream;
  }

  function stopCamera(video, stream) {
    if (stream) stream.getTracks().forEach(function (track) { track.stop(); });
    if (video) {
      video.srcObject = null;
      video.classList.remove("live");
    }
  }

  function capture(video) {
    return new Promise(function (resolve, reject) {
      var width = video.videoWidth || 0;
      var height = video.videoHeight || 0;
      if (!width || !height) {
        reject(new Error("The camera is not ready yet. Wait a moment and try again."));
        return;
      }
      var scale = Math.min(1, 640 / width);
      var canvas = document.createElement("canvas");
      canvas.width = Math.round(width * scale);
      canvas.height = Math.round(height * scale);
      var context = canvas.getContext("2d");
      context.drawImage(video, 0, 0, canvas.width, canvas.height);
      canvas.toBlob(function (blob) {
        if (blob) resolve(blob);
        else reject(new Error("Could not capture the camera image."));
      }, "image/jpeg", 0.9);
    });
  }

  async function postFace(url, blobs, fields) {
    var form = new FormData();
    form.append("csrf_token", csrfToken());
    blobs.forEach(function (blob) { form.append("face_image", blob, "face.jpg"); });
    Object.keys(fields || {}).forEach(function (key) { form.append(key, fields[key]); });
    var response = await fetch(url, {
      method: "POST",
      body: form,
      headers: {"Accept": "application/json"}
    });
    var data;
    try {
      data = await response.json();
    } catch (error) {
      throw new Error("The server returned an unexpected response. Please try again.");
    }
    if (!response.ok || !data.ok) {
      throw new Error(data.error || "Face recognition failed. Please try again.");
    }
    return data;
  }

  // ---------------------------------------------------------------------
  // Login page: password / Face ID tabs
  // ---------------------------------------------------------------------
  (function initLoginFace() {
    var video = document.getElementById("login-face-video");
    if (!video) return;
    var placeholder = document.getElementById("login-face-placeholder");
    var startButton = document.getElementById("login-face-start");
    var scanButton = document.getElementById("login-face-scan");
    var status = document.getElementById("login-face-status");
    var stream = null;
    var busy = false;

    async function start() {
      if (stream) return;
      setStatus(status, "Starting camera...", "");
      try {
        stream = await startCamera(video, placeholder);
        startButton.textContent = "Stop camera";
        scanButton.disabled = false;
        setStatus(status, "Camera ready. Look straight at the camera.", "ok");
      } catch (error) {
        setStatus(status, cameraError(error), "error");
      }
    }

    function stop() {
      stopCamera(video, stream);
      stream = null;
      startButton.textContent = "Start camera";
      scanButton.disabled = true;
      if (placeholder) placeholder.hidden = false;
    }

    startButton.addEventListener("click", function () {
      if (stream) stop();
      else start();
    });

    scanButton.addEventListener("click", async function () {
      if (busy || !stream) return;
      busy = true;
      scanButton.disabled = true;
      setStatus(status, "Scanning your face...", "");
      try {
        var blob = await capture(video);
        var data = await postFace("/login/face" + window.location.search, [blob]);
        if (data.redirect) {
          setStatus(status, "Face recognized. Opening PawTrack...", "ok");
          window.location.href = data.redirect;
          return;
        }
        setStatus(status, "Face not recognized. Please try again.", "error");
      } catch (error) {
        setStatus(status, error.message, "error");
      } finally {
        busy = false;
        if (stream) scanButton.disabled = false;
      }
    });

    document.querySelectorAll("[data-auth-tab]").forEach(function (tab) {
      tab.addEventListener("click", function () {
        if (tab.dataset.authTab !== "face") stop();
      });
    });
  })();

  // ---------------------------------------------------------------------
  // Settings page: register a face
  // ---------------------------------------------------------------------
  (function initEnrollFace() {
    var video = document.getElementById("enroll-face-video");
    if (!video) return;
    var placeholder = document.getElementById("enroll-face-placeholder");
    var startButton = document.getElementById("enroll-face-start");
    var captureButton = document.getElementById("enroll-face-capture");
    var passwordInput = document.getElementById("face_password");
    var status = document.getElementById("enroll-face-status");
    var stream = null;
    var busy = false;

    async function start() {
      if (stream) return;
      setStatus(status, "Starting camera...", "");
      try {
        stream = await startCamera(video, placeholder);
        startButton.textContent = "Stop camera";
        captureButton.disabled = false;
        setStatus(status, "Camera ready. Keep your face inside the frame.", "ok");
      } catch (error) {
        setStatus(status, cameraError(error), "error");
      }
    }

    function stop() {
      stopCamera(video, stream);
      stream = null;
      startButton.textContent = "Start camera";
      captureButton.disabled = true;
      if (placeholder) placeholder.hidden = false;
    }

    startButton.addEventListener("click", function () {
      if (stream) stop();
      else start();
    });

    captureButton.addEventListener("click", async function () {
      if (busy || !stream) return;
      var password = passwordInput ? passwordInput.value : "";
      if (!password) {
        setStatus(status, "Enter your current password first.", "error");
        if (passwordInput) passwordInput.focus();
        return;
      }
      busy = true;
      captureButton.disabled = true;
      try {
        var blobs = [];
        for (var index = 0; index < 3; index += 1) {
          setStatus(status, "Capturing " + (index + 1) + " of 3...", "");
          blobs.push(await capture(video));
          if (index < 2) await wait(450);
        }
        setStatus(status, "Checking your face...", "");
        var data = await postFace("/settings/face", blobs, {password: password});
        setStatus(status, data.message || "Face ID registered.", "ok");
        var text = document.getElementById("face-status-text");
        if (text) {
          text.innerHTML = 'Status: <b style="color:var(--ok)">registered</b>'
            + (data.enrolled_at ? " on " + escapeHtml(data.enrolled_at) : "");
        }
        stop();
        setTimeout(function () { window.location.reload(); }, 1200);
      } catch (error) {
        setStatus(status, error.message, "error");
      } finally {
        busy = false;
        if (stream) captureButton.disabled = false;
      }
    });
  })();

  // ---------------------------------------------------------------------
  // Tabs (login page)
  // ---------------------------------------------------------------------
  (function initAuthTabs() {
    var tabs = document.querySelectorAll("[data-auth-tab]");
    if (!tabs.length) return;

    function show(name) {
      document.querySelectorAll("[data-auth-tab]").forEach(function (tab) {
        var active = tab.dataset.authTab === name;
        tab.classList.toggle("active", active);
        tab.setAttribute("aria-selected", active ? "true" : "false");
      });
      var passwordPanel = document.getElementById("auth-password");
      var facePanel = document.getElementById("auth-face");
      if (passwordPanel) passwordPanel.hidden = name !== "password";
      if (facePanel) facePanel.hidden = name !== "face";
    }

    tabs.forEach(function (tab) {
      tab.addEventListener("click", function (event) {
        event.preventDefault();
        show(tab.dataset.authTab);
      });
    });
  })();
})();
