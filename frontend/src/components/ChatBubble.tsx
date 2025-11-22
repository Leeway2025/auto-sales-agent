import { Box, Paper, Typography } from '@mui/material';

interface ChatBubbleProps {
    role: 'user' | 'assistant' | string;
    text: string;
}

export default function ChatBubble({ role, text }: ChatBubbleProps) {
    const isUser = role === 'user';
    return (
        <Box sx={{ alignSelf: isUser ? 'flex-end' : 'flex-start', maxWidth: '80%', mb: 2 }}>
            <Paper
                elevation={isUser ? 4 : 1}
                sx={{
                    p: 2,
                    borderRadius: 3,
                    bgcolor: isUser ? 'primary.main' : 'rgba(255,255,255,0.1)',
                    color: isUser ? 'primary.contrastText' : 'text.primary',
                    borderTopRightRadius: isUser ? 0 : 12,
                    borderTopLeftRadius: isUser ? 12 : 0,
                }}
            >
                <Typography variant="body1" sx={{ whiteSpace: 'pre-wrap' }}>
                    {text}
                </Typography>
            </Paper>
        </Box>
    );
}
