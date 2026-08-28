import signal
import re
import pytchat
import core.base_bot

class YouTubeBot(core.base_bot.BaseBot):
    def run(self):
        self.running = True
        try:
            # 1. Extração robusta do ID (Regex é melhor que split aqui)
            vid = self.channel_name.strip()
            match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", vid)
            video_id = match.group(1) if match else vid

            # 2. O Bypass (O segredo do Netrunner)
            original_signal = signal.signal
            def mock_signal(signum, handler): pass
            
            signal.signal = mock_signal 
            try:
                chat = pytchat.create(video_id=video_id)
            finally:
                signal.signal = original_signal

            self.status_update.emit(f"Frequência YouTube sintonizada: {video_id}")

            # 3. Loop principal
            while self.running and chat.is_alive():
                for c in chat.get().sync_items():
                    self.new_message.emit(c.author.name, c.message, "youtube")
                
                import time
                time.sleep(1)

        except Exception as e:
            self.status_update.emit(f"Erro YT: {e}")
        finally:
            self.running = False