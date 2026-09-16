/**
 * ChildTrack Core Application JavaScript
 * Vanilla JavaScript UI helpers for layout, touch targets, and flash messages.
 */

document.addEventListener("DOMContentLoaded", () => {
  // Auto-dismiss flash messages after 5 seconds if present
  const flashMessages = document.querySelectorAll(".flash-message");
  flashMessages.forEach((el) => {
    setTimeout(() => {
      el.style.transition = "opacity 0.5s ease";
      el.style.opacity = "0";
      setTimeout(() => el.remove(), 500);
    }, 5000);
  });
});
