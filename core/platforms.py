PLATFORM_REGISTRY = {
    "twitch": {
        "id": "twitch", "label": "Twitch", "icon": "/assets/platforms/twitch.png", "defaultColor": "#9146ff",
        "transport": "IRC", "heartbeat": "IRC PING/PONG", "events": ["subscription", "raid", "bits"],
        "requiresAuthFor": ["follow", "point_redemption"],
    },
    "youtube": {
        "id": "youtube", "label": "YouTube", "icon": "/assets/platforms/youtube.png", "defaultColor": "#ff0000",
        "transport": "pytchat", "heartbeat": "Polling do chat", "events": ["superchat", "member"],
        "requiresAuthFor": ["subscriber"],
    },
    "tiktok": {
        "id": "tiktok", "label": "TikTok", "icon": "/assets/platforms/tiktok.png", "defaultColor": "#ff2b8a",
        "transport": "TikTokLive WebSocket", "heartbeat": "Heartbeat do TikTokLive", "events": ["gift", "follow", "like", "share"],
        "requiresAuthFor": [],
    },
    "kick": {
        "id": "kick", "label": "Kick", "icon": "/assets/platforms/kick.png", "defaultColor": "#53fc18",
        "transport": "Pusher", "heartbeat": "Keepalive do Pusher", "events": ["subscription", "gift", "follow", "raid", "donation"],
        "requiresAuthFor": [],
    },
}
