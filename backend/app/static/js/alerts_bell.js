/**
 * ChildTrack Alert Bell Notification Poller
 * Fetches real active alert counts from the backend API.
 * Never fabricates mock alert counts.
 */

async function updateAlertCount() {
  const badge = document.getElementById("alert-bell-badge");
  if (!badge) return;

  try {
    const response = await fetch("/api/v1/alerts/count", {
      headers: {
        "Accept": "application/json"
      }
    });

    if (response.ok) {
      const data = await response.json();
      const count = Number(data.count || 0);

      if (count > 0) {
        badge.textContent = count > 99 ? "99+" : count.toString();
        badge.classList.add("visible");
      } else {
        badge.textContent = "0";
        badge.classList.remove("visible");
      }
    } else {
      // Graceful empty state when endpoint is not yet initialized or returns 0
      badge.textContent = "0";
      badge.classList.remove("visible");
    }
  } catch (err) {
    // Network or server unreachable: do not show fake counts
    badge.textContent = "0";
    badge.classList.remove("visible");
  }
}

document.addEventListener("DOMContentLoaded", () => {
  // Initial check
  updateAlertCount();

  // Periodic poll every 30 seconds for alerts update
  setInterval(updateAlertCount, 30000);
});
