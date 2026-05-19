(function () {
    let audioContext = null;

    function getAudioContext() {
        const AudioContextCtor = window.AudioContext || window.webkitAudioContext;
        if (!AudioContextCtor) return null;
        if (!audioContext) audioContext = new AudioContextCtor();
        return audioContext;
    }

    function unlockAudio() {
        const context = getAudioContext();
        if (context?.state === "suspended") {
            context.resume().catch(() => {});
        }
    }

    function playTone(context, frequency, start, duration, options = {}) {
        const oscillator = context.createOscillator();
        const gain = context.createGain();
        oscillator.type = options.type || "sine";
        oscillator.frequency.setValueAtTime(frequency, start);
        if (options.endFrequency) {
            oscillator.frequency.exponentialRampToValueAtTime(options.endFrequency, start + duration);
        }
        gain.gain.setValueAtTime(0.0001, start);
        gain.gain.exponentialRampToValueAtTime(options.gain || 0.18, start + 0.015);
        gain.gain.exponentialRampToValueAtTime(0.0001, start + duration);
        oscillator.connect(gain);
        gain.connect(context.destination);
        oscillator.start(start);
        oscillator.stop(start + duration + 0.03);
    }

    function playBell() {
        const context = getAudioContext();
        if (!context) return;
        context.resume().catch(() => {});
        const now = context.currentTime + 0.02;
        playTone(context, 1046.5, now, 0.45, { gain: 0.14 });
        playTone(context, 1568, now + 0.03, 0.5, { gain: 0.08 });
        playTone(context, 784, now + 0.42, 0.42, { gain: 0.12 });
        playTone(context, 1174.7, now + 0.45, 0.45, { gain: 0.07 });
    }

    function playHorn() {
        const context = getAudioContext();
        if (!context) return;
        context.resume().catch(() => {});
        const now = context.currentTime + 0.02;
        playTone(context, 196, now, 0.28, { type: "sawtooth", gain: 0.12, endFrequency: 174.6 });
        playTone(context, 130.8, now, 0.28, { type: "square", gain: 0.05, endFrequency: 116.5 });
        playTone(context, 220, now + 0.36, 0.35, { type: "sawtooth", gain: 0.13, endFrequency: 196 });
        playTone(context, 146.8, now + 0.36, 0.35, { type: "square", gain: 0.05, endFrequency: 130.8 });
    }

    document.addEventListener("pointerdown", unlockAudio, { once: true });
    document.addEventListener("keydown", unlockAudio, { once: true });

    window.PRATO_ALERT_SOUNDS = {
        bell: playBell,
        horn: playHorn,
    };
})();
