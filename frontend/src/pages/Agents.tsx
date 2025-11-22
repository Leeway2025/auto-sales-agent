import { useEffect, useState } from 'react'
import { Link as RouterLink } from 'react-router-dom'
import { Card, CardContent, Typography, Grid, Button, Skeleton, Box } from '@mui/material'
import { ChatBubbleOutline } from '@mui/icons-material'
import { api } from '../api'

type Agent = { id: string; name?: string; description?: string; created_at?: number }

export default function Agents() {
  const [items, setItems] = useState<Agent[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    (async () => {
      try {
        const data = await api.getAgents()
        setItems(data)
      } catch (e) {
        console.error(e)
      } finally { setLoading(false) }
    })()
  }, [])

  return (
    <Box>
      <Typography variant="h4" gutterBottom fontWeight="bold" sx={{ mb: 4 }}>
        我的 Agents
      </Typography>

      {loading ? (
        <Grid container spacing={3}>
          {[1, 2, 3].map(i => (
            <Grid size={{ xs: 12, sm: 6, md: 4 }} key={i}>
              <Skeleton variant="rectangular" height={140} sx={{ borderRadius: 4 }} />
            </Grid>
          ))}
        </Grid>
      ) : (
        <Grid container spacing={3}>
          {items.map(a => (
            <Grid size={{ xs: 12, sm: 6, md: 4 }} key={a.id}>
              <Card sx={{ height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'space-between', transition: 'transform 0.2s', '&:hover': { transform: 'translateY(-4px)' } }}>
                <CardContent>
                  <Typography variant="h6" gutterBottom fontWeight="bold">
                    {a.name || '销售助手'}
                  </Typography>
                  {a.description && (
                    <Typography variant="body2" color="text.secondary" gutterBottom sx={{ mb: 2, minHeight: '40px' }}>
                      {a.description}
                    </Typography>
                  )}
                  <Typography variant="body2" color="text.secondary" gutterBottom>
                    {a.created_at
                      ? new Date(a.created_at * 1000).toLocaleString('zh-CN', {
                        year: 'numeric',
                        month: '2-digit',
                        day: '2-digit',
                        hour: '2-digit',
                        minute: '2-digit'
                      })
                      : '创建时间未知'
                    }
                  </Typography>
                  <Typography variant="caption" color="text.secondary" display="block">
                    ID: {a.id.slice(0, 12)}...
                  </Typography>
                </CardContent>
                <Box sx={{ p: 2, pt: 0 }}>
                  <Button
                    component={RouterLink}
                    to={`/chat/${a.id}`}
                    variant="outlined"
                    fullWidth
                    startIcon={<ChatBubbleOutline />}
                  >
                    聊天
                  </Button>
                </Box>
              </Card>
            </Grid>
          ))}
        </Grid>
      )}
    </Box>
  )
}

