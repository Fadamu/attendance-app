// Small client-side enhancements
document.addEventListener("DOMContentLoaded", () => {
    const forms = document.querySelectorAll("form");
    forms.forEach(form => {
        form.addEventListener("submit", () => {
            const button = form.querySelector("button[type='submit']");
            if (button && !form.getAttribute("onsubmit")) {
                button.disabled = true;
                button.style.opacity = ".7";
            }
        });
    });
});