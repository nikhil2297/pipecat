import time
class CallStats:
    """Class to track call statistics"""
    def __init__(self):
        self.call_start_time = time.time()
        self.call_end_time = None
        self.silence_events = 0
        self.user_speech_events = 0
        self.bot_speech_events = 0
        self.prompts_sent = 0
    
    def duration_seconds(self):
        """Return the call duration in seconds"""
        end_time = self.call_end_time if self.call_end_time else time.time()
        return end_time - self.call_start_time
    
    def format_duration(self):
        """Format the duration as mm:ss"""
        seconds = int(self.duration_seconds())
        minutes, seconds = divmod(seconds, 60)
        return f"{minutes}:{seconds:02d}"
    
    def generate_summary(self):
        """Generate a summary of call statistics"""
        duration = self.format_duration()
        summary = [
            "=== CALL SUMMARY ===",
            f"Duration: {duration}",
            f"Silence events: {self.silence_events}",
            f"Prompts sent: {self.prompts_sent}",
            f"User speech events: {self.user_speech_events}",
            f"Bot speech events: {self.bot_speech_events}"
        ]
        return "\n".join(summary)