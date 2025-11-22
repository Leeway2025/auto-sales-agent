const USER_ID = 'demo-user';

export class ApiError extends Error {
    constructor(public status: number, message: string) {
        super(message);
        this.name = 'ApiError';
    }
}

async function handleResponse<T>(response: Response): Promise<T> {
    if (!response.ok) {
        const text = await response.text();
        throw new ApiError(response.status, text || 'API request failed');
    }
    return response.json();
}

export const api = {
    // Agents
    getAgents: async () => {
        const res = await fetch(`/api/agents?user_id=${USER_ID}`);
        return handleResponse<any[]>(res);
    },

    // Speech
    getSpeechToken: async () => {
        const res = await fetch('/api/speech/token');
        return handleResponse<{ token: string; region: string }>(res);
    },

    // Onboard (File Upload)
    uploadAudio: async (file: File) => {
        const fd = new FormData();
        fd.append('file', file);
        const res = await fetch('/api/upload', { method: 'POST', body: fd });
        return handleResponse<{ filename: string; transcript: string }>(res);
    },

    generateAgent: async (transcript: string) => {
        const res = await fetch('/api/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ transcript, user_id: USER_ID }),
        });
        return handleResponse<{ agent_id: string; prompt: string }>(res);
    },

    // Chat
    chat: async (agentId: string, message: string, history: any[]) => {
        const res = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ agent_id: agentId, message, history, user_id: USER_ID }),
        });
        return handleResponse<{ reply: string }>(res);
    },

    chatWithAgent: async (agentId: string, message: string, threadId?: string) => {
        const res = await fetch(`/api/agents/${agentId}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message, thread_id: threadId }),
        });
        return handleResponse<{ reply: string; thread_id: string }>(res);
    },

    // Streaming chat with SSE
    chatWithAgentStream: (
        agentId: string,
        message: string,
        threadId: string | undefined,
        onChunk: (content: string) => void,
        onComplete: (threadId: string) => void,
        onError: (error: string) => void
    ) => {
        const url = new URL(`/api/agents/${agentId}/chat/stream`, window.location.origin);

        fetch(url.toString(), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message, thread_id: threadId }),
        }).then(async (response) => {
            if (!response.ok) {
                throw new Error('Stream request failed');
            }

            const reader = response.body?.getReader();
            const decoder = new TextDecoder();

            if (!reader) {
                throw new Error('No reader available');
            }

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                const chunk = decoder.decode(value);
                const lines = chunk.split('\n');

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const data = JSON.parse(line.slice(6));

                            if (data.error) {
                                onError(data.error);
                                return;
                            }

                            if (data.done) {
                                if (data.thread_id) {
                                    onComplete(data.thread_id);
                                }
                                return;
                            }

                            if (data.content) {
                                onChunk(data.content);
                            }
                        } catch (e) {
                            // Ignore parse errors for incomplete chunks
                        }
                    }
                }
            }
        }).catch((error) => {
            onError(error.message || 'Streaming failed');
        });
    },

    // Onboard Session
    startSession: async (seedTranscript?: string) => {
        const res = await fetch('/api/onboard_session/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ seed_transcript: seedTranscript || null, user_id: USER_ID }),
        });
        return handleResponse<{ session: any; reply: string }>(res);
    },

    sendMessageToSession: async (sessionId: string, message: string) => {
        const res = await fetch(`/api/onboard_session/${sessionId}/message`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message, user_id: USER_ID }),
        });
        return handleResponse<{ session: any; reply: string; done: boolean }>(res);
    },

    finalizeSession: async (sessionId: string) => {
        const res = await fetch(`/api/onboard_session/${sessionId}/finalize`, { method: 'POST' });
        return handleResponse<{ agent_id: string; prompt: string; profile: any; has_voice_template: boolean }>(res);
    },

    uploadVoiceTemplate: async (sessionId: string, audioBlob: Blob) => {
        const formData = new FormData();
        formData.append('audio', audioBlob, 'voice_template.wav');

        const res = await fetch(`/api/onboard_session/${sessionId}/voice_template`, {
            method: 'POST',
            body: formData,
        });
        return handleResponse<{ success: boolean; message: string }>(res);
    },

    // CosyVoice TTS
    synthesizeSpeech: async (text: string, speaker: string = 'default', speed: number = 1.0) => {
        const formData = new FormData();
        formData.append('text', text);
        formData.append('speaker', speaker);
        formData.append('speed', speed.toString());

        const res = await fetch('/api/tts', {
            method: 'POST',
            body: formData,
        });

        if (!res.ok) {
            throw new ApiError(res.status, 'TTS failed');
        }

        return res.blob();
    },

    cloneVoice: async (text: string, referenceAudio: Blob, speed: number = 1.0) => {
        const formData = new FormData();
        formData.append('text', text);
        formData.append('reference_audio', referenceAudio, 'reference.wav');
        formData.append('speed', speed.toString());

        const res = await fetch('/api/tts/clone', {
            method: 'POST',
            body: formData,
        });

        if (!res.ok) {
            throw new ApiError(res.status, 'Voice cloning failed');
        }

        return res.blob();
    },

    getTTSSpeakers: async () => {
        const res = await fetch('/api/tts/speakers');
        return handleResponse<{ speakers: Array<{ id: string; name: string }> }>(res);
    },

    checkTTSHealth: async () => {
        const res = await fetch('/api/tts/health');
        return handleResponse<{ healthy: boolean; enabled: boolean; url: string }>(res);
    },
};
