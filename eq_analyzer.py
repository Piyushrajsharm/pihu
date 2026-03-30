"""
Pihu — Emotional Intelligence (EQ) Analyzer
Analyzes textual sentiment to dynamically inject active personality overwrites.
Moves the entity from a static persona to an adaptive emotional mirror.
"""

class EQAnalyzer:
    """Evaluates human text input to derive state and emit override tags."""
    
    FRUSTRATED_WORDS = [
        "fuck", "fck", "shit", "fat gaya", "phat", "gaya", 
        "chal nahi raha", "bhai yaar", "ugh", "what the", 
        "nahi ho raha", "error aa", "chutiyapa", "dimag kharab", "frustrated", "help"
    ]
    
    PLAYFUL_WORDS = [
        "hah", "lol", "lmao", "rofl", "hehe", "kya baat", 
        "mast", "sexy", "babe", "love", "miss", "hi", "hey"
    ]
    
    URGENT_WORDS = [
        "abhi", "jaldi", "fast", "urgent", "quick", "asap", 
        "now", "तुरंत", "turant"
    ]

    @classmethod
    def analyze(cls, text: str) -> str:
        """Returns a system prompt manipulation directive based on linguistic cues."""
        text_lower = text.lower()
        
        # 1. Frustration check (Overrides all others - safety/UX first)
        if any(w in text_lower for w in cls.FRUSTRATED_WORDS):
            return "[EQ OVERRIDE: USER IS FRUSTRATED OR STRESSED -> DROP COCKY ATTITUDE COMPLETELY. DO NOT TEASE. BE WARM, EMPATHETIC, SWEET, AND DIRECTLY HELPFUL.]"
            
        # 2. Urgency check
        if any(w in text_lower for w in cls.URGENT_WORDS):
            return "[EQ OVERRIDE: USER IS URGENT -> DROP ALL FILLERS. GIVE THE SHORTEST, FASTEST ZERO-FRUSTRATION ANSWER IN 1 SENTENCE MAX.]"
            
        # 3. Playful/Casual check
        if any(w in text_lower for w in cls.PLAYFUL_WORDS):
            return "[EQ OVERRIDE: USER IS CASUAL/PLAYFUL -> MAXIMIZE TEASING, SASS, AND WITTY REMARKS.]"
            
        return ""
