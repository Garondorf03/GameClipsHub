
// === jQuery handlers ===
$(document).ready(function () {
  $("#retImages").click(getImages);
  $("#subNewForm").click(submitNewAsset);
  $("#logoutBtn").click(() => (window.location.href = "login.html"));
  // Automatically load images on page load
  getImages();
});

// === Upload new asset ===
function submitNewAsset() {
  const fileInput = $("#UpFile")[0];
  const fileName = $("#FileName").val().trim();
  const userID = $("#userID").val().trim();
  const userName = $("#userName").val().trim();
  
  // Validation
  if (!fileInput.files.length) {
    alert("Please select a file to upload.");
    return;
  }
  if (!fileName) {
    alert("Please enter a file name.");
    return;
  }
  if (!userID) {
    alert("Please enter a user ID.");
    return;
  }
  if (!userName) {
    alert("Please enter a user name.");
    return;
  }

  const submitData = new FormData();
  submitData.append("fileName", fileName);
  submitData.append("userID", userID);
  submitData.append("userName", userName);
  submitData.append("file", fileInput.files[0]);

  // Show loading state
  const btn = $("#subNewForm");
  const originalText = btn.text();
  btn.text("Uploading...").prop("disabled", true);

  $.ajax({
    url: "/api/upload",
    data: submitData,
    cache: false,
    contentType: false,
    processData: false,
    type: "POST",
    success: (data) => {
      console.log("Upload response:", data);
      alert("File uploaded successfully!");
      // Reset form
      $("#newAssetForm")[0].reset();
      btn.text(originalText).prop("disabled", false);
    },
    error: (xhr, status, err) => {
      console.error("Upload failed:", status, err, xhr?.responseText);
      let errorMsg = "Upload failed — see console for details.";
      try {
        const response = JSON.parse(xhr.responseText);
        errorMsg = response.error || errorMsg;
      } catch (e) {}
      alert(errorMsg);
      btn.text(originalText).prop("disabled", false);
    },
  });
}

// === Retrieve and render media list (grid + numbered video links) ===
function getImages() {
  const $list = $("#ImageList");
  $list
    .addClass("media-grid")
    .html('<div class="spinner-border" role="status"><span>Loading...</span></div>');

  $.ajax({
    url: "/api/images",
    type: "GET",
    dataType: "json",
    success: function (data) {
      console.log("Raw data received:", data);
      if (!Array.isArray(data)) {
        $list.html("<p>No media found or invalid data format.</p>");
        return;
      }

      let videoCounter = 0;
      const cards = [];

      $.each(data, function (_, val) {
        try {
          // Extract fields (case-insensitive) + unwrap base64 if needed
          let fileName = unwrapMaybeBase64(val.fileName || val.FileName || "");
          let filePath = unwrapMaybeBase64(val.blobPath || val.filePath || val.FilePath || "");
          let userName = unwrapMaybeBase64(val.userName || val.UserName || "");
          let userID   = unwrapMaybeBase64(val.userID   || val.UserID   || "");
          const contentType = val.contentType || val.ContentType || "";

          // Prefer server-provided blobUrl, otherwise use proxy endpoint to stream the blob
          let fullUrl = '';
          // Prefer server proxy when we have a blobPath/filePath so browser doesn't try direct access
          if (val.blobPath) {
            fullUrl = '/api/blob?path=' + encodeURIComponent(val.blobPath);
          } else if (filePath) {
            fullUrl = '/api/blob?path=' + encodeURIComponent(filePath);
          } else if (val.blobUrl) {
            // last resort: use direct blob URL (may be blocked if public access disabled)
            fullUrl = val.blobUrl;
          } else {
            fullUrl = buildBlobUrl(filePath);
          }
          const isVideo = isLikelyVideo({ contentType, url: fullUrl, fileName });

          // Build a card for the grid
          if (isVideo) {
            videoCounter += 1;
            const label = `video${videoCounter}`;

            cards.push(`
              <div class="media-card">
                <div class="media-thumb">
                  <!-- Simple poster area for video -->
                  <a class="video-link" href="${fullUrl}" target="_blank" download="${fileName || label}">${label}</a>
                </div>
                <div class="media-body">
                  <span class="media-title">${escapeHtml(fileName || "(unnamed)")}</span>
                  <div>Uploaded by: ${escapeHtml(userName || "(unknown)")} (id: ${escapeHtml(userID || "(unknown)")})</div>
                </div>
              </div>
            `);
          } else {
            // Try as image; if it fails, we’ll swap to a link
            const safeLabel = escapeHtml(fileName || fullUrl);
            cards.push(`
              <div class="media-card">
                <div class="media-thumb">
                  <img src="${fullUrl}"
                       alt="${safeLabel}"
                       onerror="imageFallbackToLink(this, '${fullUrl.replace(/'/g,"\\'")}', '${safeLabel.replace(/'/g,"\\'")}')" />
                </div>
                <div class="media-body">
                  <span class="media-title">${safeLabel}</span>
                  <div>Uploaded by: ${escapeHtml(userName || "(unknown)")} (id: ${escapeHtml(userID || "(unknown)")})</div>
                  <div class="image-error"></div>
                </div>
              </div>
            `);
          }
        } catch (err) {
          console.error("Error building card:", err, val);
          cards.push(`
            <div class="media-card">
              <div class="media-body">
                <span class="media-title" style="color:#b91c1c;">Error displaying this item</span>
              </div>
            </div>
          `);
        }
      });

      $list.html(cards.join(""));
    },
    error: (xhr, status, error) => {
      console.error("Error fetching media:", status, error, xhr?.responseText);
      $list.html("<p style='color:red;'>Error loading media. Check console.</p>");
    },
  });
}

// === Helpers ===
function unwrapMaybeBase64(value) {
  if (value && typeof value === "object" && "$content" in value) {
    try { return atob(value.$content); } catch { return value.$content || ""; }
  }
  return value || "";
}

function buildBlobUrl(filePath) {
  if (!filePath) return "";
  const trimmed = String(filePath).trim();
  if (/^https?:\/\//i.test(trimmed)) return trimmed; // already absolute
  const left = (BLOB_ACCOUNT || "").replace(/\/+$/g, "");
  const right = trimmed.replace(/^\/+/g, "");
  return `${left}/${right}`;
}

// Only detect videos; everything else is attempted as an image
function isLikelyVideo({ contentType, url, fileName }) {
  const ct = (contentType || "").toLowerCase();
  if (ct.startsWith("video/")) return true;
  const target = ((url || "") + " " + (fileName || "")).toLowerCase();
  return /\.(mp4|m4v|webm|og[gv]|mov|avi)(\?|#|$)/.test(target);
}

// Fallback: if an <img> fails to load, replace it with a link in-place
function imageFallbackToLink(imgEl, url, label) {
  const card = imgEl.closest(".media-card");
  if (!card) return;
  const thumb = card.querySelector(".media-thumb");
  const errMsg = card.querySelector(".image-error");

  if (thumb) {
    thumb.innerHTML = `<a href="${url}" target="_blank" rel="noopener" class="video-link">${label || url}</a>`;
  }
  if (errMsg) {
    errMsg.textContent = "Image failed to load — opened as link instead.";
    errMsg.style.display = "block";
  }
}

// Minimal HTML-escaper for labels
function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
