const form = document.querySelector("#chat-form");
const input = document.querySelector("#message-input");
const messages = document.querySelector("#messages");

form?.addEventListener("submit", (event) => {
  event.preventDefault();

  const value = input.value.trim();
  if (!value) {
    return;
  }

  const message = document.createElement("p");
  message.className = "message";
  message.textContent = value;
  messages.append(message);
  input.value = "";
});
