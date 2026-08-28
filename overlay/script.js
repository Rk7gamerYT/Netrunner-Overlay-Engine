const renderedMessages = new Set();


function escapeHtml(text) {

    const div = document.createElement("div");

    div.innerText = text;

    return div.innerHTML;
}


function addChatMessage(

    from,
    message,
    platform = "default"
) {

    const template = document
        .getElementById("chatlist_item")
        .innerHTML;

    const colors = {

        twitch: "#9146ff",

        youtube: "#ff0000",

        tiktok: "#ff0050",

        kick: "#53fc18",

        default: "#ff4d4d"
    };

    const color =
        colors[platform] || colors.default;

    const html = template

        .replace(
            /{from}/g,
            escapeHtml(from)
        )

        .replace(
            /{message}/g,
            escapeHtml(message)
        )

        .replace(
            /{color}/g,
            color
        )

        .replace(
            /{platform}/g,
            platform
        )

        .replace(
            /{messageId}/g,
            Date.now()
        );

    const wrapper = document.createElement("div");

    wrapper.innerHTML = html;

    const log =
        document.getElementById("log");

    const element =
        wrapper.firstElementChild;

    log.appendChild(element);

    while (log.children.length > 50) {

        log.removeChild(
            log.firstChild
        );
    }

    log.scrollTop = log.scrollHeight;
}


async function updateChat() {

    try {

        const response = await fetch(
            "/chat?t=" + Date.now()
        );

        const data = await response.json();

        data.forEach(msg => {

            const id = btoa(

                `${msg.platform}-${msg.user}-${msg.message}`
            );

            if (renderedMessages.has(id)) {
                return;
            }

            renderedMessages.add(id);

            addChatMessage(

                msg.user,

                msg.message,

                msg.platform
            );
        });

    } catch (e) {

        console.error(
            "Overlay Error:",
            e
        );
    }
}

setInterval(updateChat, 500);