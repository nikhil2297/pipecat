import time
import asyncio
from call_stats import CallStats
from loguru import logger

from pipecat.frames.frames import (
    BotStoppedSpeakingFrame,
    UserStartedSpeakingFrame,
    EndTaskFrame,
    TextFrame,  # ✅ This is used to pass the TTS utterance directly
)
from pipecat.processors.frame_processor import FrameProcessor, FrameDirection
from pprint import pprint


class SilenceWatcher(FrameProcessor):
    def __init__(self, tts, session_manager, prompt_text="Are you still there?", threshold_secs=10, max_prompts=3):
        super().__init__()
        self.tts = tts
        self.task = None
        self.session_manager = session_manager
        self.prompt_text = prompt_text
        self.threshold_secs = threshold_secs
        self.max_prompts = max_prompts

        # Monitoring state
        self.awaiting_response = False
        self.last_bot_spoke_time = None
        self.unanswered_count = 0
        self.monitoring_active = True
        
        # Stats tracking
        self.stats = CallStats()
        
        # Start the silence monitoring loop
        self.loop_task = asyncio.create_task(self._monitor_silence())
        logger.info(f"[SilenceWatcher] Initialized with {threshold_secs}s threshold and {max_prompts} max prompts")
    
    def set_task(self, task):
        """Set the pipeline task reference"""
        self.task = task

    async def _monitor_silence(self):
        """Continuously monitor for silence after bot speaks"""
        logger.debug("[SilenceWatcher] Starting silence monitoring loop")
        while self.monitoring_active:
            await asyncio.sleep(1)  # Check every second
            
            # Only check for silence when we're awaiting a response and have a timestamp
            if self.awaiting_response and self.last_bot_spoke_time:
                elapsed = time.time() - self.last_bot_spoke_time
                
                # If silence threshold exceeded, take action
                if elapsed > self.threshold_secs:
                    logger.info(f"[SilenceWatcher] Detected {elapsed:.1f}s of silence after bot spoke")
                    self.awaiting_response = False  # Reset flag so we don't trigger multiple times
                    self.unanswered_count += 1
                    self.stats.silence_events += 1
                    self.stats.prompts_sent += 1
                    
                    logger.info(f"[SilenceWatcher] Sending prompt #{self.unanswered_count}: '{self.prompt_text}'")
                    

                    # Create and send the prompt as a text frame
                    text_frame = TextFrame(self.prompt_text)
                    await asyncio.sleep(2)
                    await self.tts.process_frame(text_frame, FrameDirection.DOWNSTREAM)
                    
                    
                    # Reset the timer for the next silence period after this prompt
                    self.last_bot_spoke_time = time.time()
                    self.awaiting_response = True
                    
                    # End the call if max prompts reached
                    if self.unanswered_count >= self.max_prompts:
                        logger.warning(f"[SilenceWatcher] Max prompts ({self.max_prompts}) reached without response, terminating call")
                        await self.terminate_call()

    async def terminate_call(self):
        """Gracefully terminate the call with summary"""
        # Record call end time
        self.stats.call_end_time = time.time()
        
        # Log call summary
        summary = self.stats.generate_summary()
        logger.info(summary)
        
        # Mark call as terminated
        self.session_manager.call_flow_state.set_call_terminated()
        
        # Stop monitoring
        self.monitoring_active = False
        
        # End the pipeline task
        await self.push_frame(EndTaskFrame(), FrameDirection.UPSTREAM)

    async def process_frame(self, frame, direction):
        """Process incoming frames to detect bot/user speech events"""
        await super().process_frame(frame, direction)
        
        if isinstance(frame, BotStoppedSpeakingFrame):
            logger.debug("[SilenceWatcher] Bot stopped speaking, starting silence timer")
            self.awaiting_response = True
            self.last_bot_spoke_time = time.time()
            self.stats.bot_speech_events += 1
            
        elif isinstance(frame, UserStartedSpeakingFrame):
            logger.debug("[SilenceWatcher] User started speaking - resetting silence state")
            self.awaiting_response = False
            self.unanswered_count = 0
            self.stats.user_speech_events += 1
            
        await self.push_frame(frame, direction)
    
    async def cleanup(self):
        """Cleanup method to stop the monitoring task"""
        logger.debug("[SilenceWatcher] Cleaning up resources")
        # Generate final stats if not already done
        if not self.stats.call_end_time:
            self.stats.call_end_time = time.time()
            summary = self.stats.generate_summary()
            logger.info(summary)
            
        self.monitoring_active = False
        if self.loop_task and not self.loop_task.done():
            self.loop_task.cancel()
            try:
                await self.loop_task
            except asyncio.CancelledError:
                pass