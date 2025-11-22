import { Routes, Route, Link as RouterLink } from 'react-router-dom'
import { Suspense, lazy } from 'react'
import { AppBar, Toolbar, Typography, Container, Box, Link, Stack, CircularProgress } from '@mui/material'
import Onboard from './pages/Onboard'
import Agents from './pages/Agents'
import OnboardSession from './pages/OnboardSession'

const Chat = lazy(() => import('./pages/Chat'))

export default function App() {
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      <AppBar position="sticky">
        <Toolbar>
          <Typography variant="h6" component={RouterLink} to="/" sx={{ flexGrow: 1, textDecoration: 'none', color: 'inherit', fontWeight: 800, letterSpacing: '.5px' }}>
            Voice Agent Studio
          </Typography>
          <Stack direction="row" spacing={3}>
            <Link component={RouterLink} to="/agents" color="inherit" underline="none" sx={{ '&:hover': { color: 'secondary.main' } }}>
              Agents
            </Link>
            <Link component={RouterLink} to="/onboard-session" color="inherit" underline="none" sx={{ '&:hover': { color: 'secondary.main' } }}>
              向导上架
            </Link>
            <Link href="https://azure.microsoft.com/" target="_blank" color="inherit" underline="none" sx={{ '&:hover': { color: 'secondary.main' } }}>
              Azure
            </Link>
          </Stack>
        </Toolbar>
      </AppBar>

      <Container maxWidth="lg" sx={{ mt: 5, mb: 5, flex: 1 }}>
        <Suspense fallback={<Box display="flex" justifyContent="center" mt={10}><CircularProgress /></Box>}>
          <Routes>
            <Route path="/" element={<Onboard />} />
            <Route path="/agents" element={<Agents />} />
            <Route path="/onboard-session" element={<OnboardSession />} />
            <Route path="/chat/:id" element={<Chat />} />
          </Routes>
        </Suspense>
      </Container>

      <Box component="footer" sx={{ py: 3, textAlign: 'center', opacity: 0.6 }}>
        <Typography variant="body2">Built By Wei</Typography>
      </Box>
    </Box>
  )
}
