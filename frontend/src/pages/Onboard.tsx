import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Markdown from 'react-markdown'
import { Card, CardContent, Typography, Button, Box, Stack, LinearProgress, Alert, Paper, Divider, Chip, Link, TextField } from '@mui/material'
import { Mic, Stop, CloudUpload, AutoAwesome, PlayArrow, Send, CheckCircle, LibraryMusic } from '@mui/icons-material'
import { api } from '../api'
import { useSpeechSDK } from '../hooks/useSpeechSDK'

type SessionState = {
  session_id: string
  user_id: string
  created_at: number
  fields: Record<string, string | null>
  missing: string[]
  history: { role: string; text: string }[]
}

type Msg = { role: 'assistant' | 'user'; text: string }

export default function Onboard() {
  const [file, setFile] = useState<File | null>(null)
  const [transcript, setTranscript] = useState('')
  const [session, setSession] = useState<SessionState | null>(null)
  const [msgs, setMsgs] = useState<Msg[]>([])
  const [input, setInput] = useState('')
  const [done, setDone] = useState(false)
  const [created, setCreated] = useState<{ agentId: string; prompt: string } | null>(null)
  const [loading, setLoading] = useState(false)
  const [hasVoiceTemplate, setHasVoiceTemplate] = useState(false)
  const [templateFile, setTemplateFile] = useState<File | null>(null)
  const nav = useNavigate()

  const { startRecognition, stopRecognition, isRecording, ready } = useSpeechSDK()
  const chunksRef = useRef<string[]>([])

  const handleStartRec = () => {
    if (!ready) return alert('语音引擎尚未就绪')
    setTranscript('')
    chunksRef.current = []
    startRecognition(
      (text) => {
        if (text) {
          chunksRef.current.push(text)
          setTranscript(chunksRef.current.join(' '))
        }
      },
      (text) => {
        const preview = (chunksRef.current.length ? chunksRef.current.join(' ') + ' ' : '') + text
        setTranscript(preview)
      }
    )
  }

  const handleStopRec = () => {
    stopRecognition()
  }

  const startFromAudio = async () => {
    setLoading(true)
    try {
      let seed = transcript
      if (file) {
        const res = await api.uploadAudio(file)
        seed = res.transcript
        setTranscript(seed)
      }
      const seedText = seed.trim()
      if (!seedText) throw new Error('没有识别到文本')
      const data = await api.startSession(seedText)
      setSession(data.session)
      setMsgs([{ role: 'assistant', text: data.reply }])
      setDone((data.session.missing || []).length === 0)
      setCreated(null)
    } catch (e: any) {
      alert(e.message || '语音转写/启动失败')
    } finally {
      setLoading(false)
    }
  }

  const send = async () => {
    if (!session || !input.trim()) return
    setLoading(true)
    const sid = session.session_id
    const userText = input
    setMsgs(m => [...m, { role: 'user', text: userText }])
    setInput('')
    try {
      const data = await api.sendMessageToSession(sid, userText)
      setSession(data.session)
      setMsgs(m => [...m, { role: 'assistant', text: data.reply }])
      setDone(!!data.done)
    } catch (e: any) {
      alert(e.message || '发送失败')
    } finally { setLoading(false) }
  }

  const finalize = async () => {
    if (!session) return
    setLoading(true)
    try {
      if (templateFile) {
        const fd = new FormData()
        fd.append('audio', templateFile, templateFile.name)
        await fetch(`/api/onboard_session/${session.session_id}/voice_template`, { method: 'POST', body: fd })
        setHasVoiceTemplate(true)
      }
      const data = await api.finalizeSession(session.session_id)
      setCreated({ agentId: data.agent_id, prompt: data.prompt })
      const hasTemplate = data.has_voice_template || !!templateFile
      const msg = hasTemplate
        ? '已为你生成 Agent（含声音模板），并创建成功。你可以前往聊天页进行测试。'
        : '已为你生成 Agent，并创建成功。你可以前往聊天页进行测试。'
      setMsgs(m => [...m, { role: 'assistant', text: msg }])
    } catch (e: any) {
      alert(e.message || '生成失败')
    } finally { setLoading(false) }
  }

  const fieldsView = () => {
    if (!session) return null
    const f = session.fields || {}
    const kv = Object.entries(f).filter(([_, v]) => v)
    if (kv.length === 0) return null
    return (
      <Box sx={{ mt: 3, p: 2, bgcolor: 'rgba(255,255,255,0.05)', borderRadius: 1 }}>
        <Typography variant="subtitle2" gutterBottom sx={{ opacity: 0.7 }}>已收集信息</Typography>
        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2 }}>
          {kv.map(([k, v]) => (
            <Chip key={k} label={`${k}: ${v}`} size="small" variant="outlined" />
          ))}
        </Box>
      </Box>
    )
  }

  return (
    <Card>
      <CardContent sx={{ p: 4 }}>
        <Typography variant="h1" gutterBottom sx={{ background: 'linear-gradient(45deg, #7c3aed, #22d3ee)', backgroundClip: 'text', WebkitTextFillColor: 'transparent', mb: 2 }}>
          用语音或文本，开启多轮上架
        </Typography>
        <Typography variant="body1" color="text.secondary" sx={{ mb: 4, maxWidth: 720 }}>
          支持长音频转写 + 多轮追问收集品牌信息，并可额外上传/录制声音模板用于克隆。录音/上传用于转写文本；下方模板区用于克隆声音。
          如需纯文本起点，请前往「向导上架」。
        </Typography>

        <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} alignItems="center" sx={{ mb: 3 }}>
          <Button
            component="label"
            variant="outlined"
            startIcon={<CloudUpload />}
            sx={{ borderColor: 'rgba(255,255,255,0.2)', color: 'text.primary' }}
            aria-label="上传音频文件（长音频支持）"
          >
            {file ? file.name : '上传音频文件（长音频支持）'}
            <input type="file" hidden accept="audio/*" onChange={e => setFile(e.target.files?.[0] || null)} />
          </Button>

          {!isRecording ? (
            <Button variant="contained" color="secondary" startIcon={<Mic />} onClick={handleStartRec} disabled={loading || !ready}>
              开始录音
            </Button>
          ) : (
            <Button variant="contained" color="warning" startIcon={<Stop />} onClick={handleStopRec} disabled={loading}>
              停止录音
            </Button>
          )}

          <Button variant="contained" startIcon={<AutoAwesome />} disabled={loading || (!file && !transcript)} onClick={startFromAudio}>
            用语音开启向导
          </Button>
        </Stack>

        <Paper sx={{ p: 3, borderRadius: 3, border: '1px solid rgba(255,255,255,0.08)', background: 'rgba(255,255,255,0.03)', mb: 4 }}>
          <Typography variant="subtitle1" gutterBottom>更多方式</Typography>
          <Typography variant="body2" color="text.secondary">
            需要纯文本起点或更复杂的对话流程？请前往
            {' '}
            <Link href="/onboard-session" underline="hover" color="secondary">向导上架</Link>
            ，继续文本多轮引导。
          </Typography>
        </Paper>

        {loading && <LinearProgress sx={{ mb: 2, borderRadius: 2 }} />}

        {session && (
          <Box sx={{ mt: 2 }}>
            <Paper sx={{ maxHeight: '50vh', overflow: 'auto', p: 2, mb: 3, bgcolor: 'rgba(0,0,0,0.2)' }}>
              <Stack spacing={2}>
                {msgs.map((m, i) => (
                  <Box key={i} sx={{ display: 'flex', justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start' }}>
                    <Paper sx={{ p: 1.5, maxWidth: '80%', bgcolor: m.role === 'user' ? 'primary.main' : 'rgba(255,255,255,0.08)' }}>
                      <Typography variant="body2" sx={{ color: m.role === 'user' ? '#fff' : 'inherit' }}>
                        {m.text}
                      </Typography>
                    </Paper>
                  </Box>
                ))}
              </Stack>
            </Paper>

            <Stack direction="row" spacing={2} sx={{ mb: 2 }}>
              <TextField
                fullWidth
                placeholder="输入你的补充信息…"
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && !e.shiftKey && (e.preventDefault(), send())}
              />
              <Button variant="contained" onClick={send} disabled={loading} endIcon={<Send />}>发送</Button>
              {done && !created && (
                <Button variant="contained" color="success" onClick={finalize} disabled={loading} startIcon={<CheckCircle />}>
                  确认生成
                </Button>
              )}
            </Stack>

            <Divider />
            {fieldsView()}
          </Box>
        )}

        {transcript && !session && (
          <Paper sx={{ p: 2, mt: 2, bgcolor: 'rgba(0,0,0,0.15)' }}>
            <Typography variant="subtitle2" gutterBottom>转写结果（可用于长音频）</Typography>
            <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>{transcript}</Typography>
          </Paper>
        )}

        {session && (
          <Paper sx={{ p: 3, borderRadius: 2, mt: 2, bgcolor: 'rgba(255,255,255,0.04)' }}>
            <Typography variant="subtitle1" gutterBottom>上传/录制克隆模板（可选，推荐 3-10s 清晰语音）</Typography>
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} alignItems={{ md: 'center' }}>
              <Button
                component="label"
                variant="outlined"
                startIcon={<LibraryMusic />}
                sx={{ borderColor: 'rgba(255,255,255,0.2)', color: 'text.primary' }}
              >
                {templateFile ? templateFile.name : '上传克隆模板音频'}
                <input type="file" hidden accept="audio/*" onChange={e => setTemplateFile(e.target.files?.[0] || null)} />
              </Button>
              <Typography variant="body2" color="text.secondary">
                未上传则使用默认音色；上传后将自动随“确认生成”一起提交。
              </Typography>
            </Stack>
          </Paper>
        )}

        {created && (
          <Box sx={{ mt: 4 }}>
            <Alert severity="success" sx={{ mb: 3 }}>Agent 已创建成功！</Alert>
            <Box sx={{ display: 'grid', gridTemplateColumns: { md: '1fr 1fr' }, gap: 3 }}>
              <Paper sx={{ p: 3, bgcolor: 'rgba(0,0,0,0.2)', borderRadius: 3 }}>
                <Typography variant="h6" gutterBottom>Agent ID</Typography>
                <Paper sx={{ p: 2, bgcolor: 'rgba(0,0,0,0.2)', fontFamily: 'monospace' }}>{created.agentId}</Paper>
                <Button variant="contained" color="success" sx={{ mt: 2 }} onClick={() => nav(`/chat/${created.agentId}`)} startIcon={<PlayArrow />}>
                  前往聊天测试
                </Button>
              </Paper>
              <Paper sx={{ p: 3, bgcolor: 'rgba(0,0,0,0.2)', borderRadius: 3 }}>
                <Typography variant="h6" gutterBottom>系统提示词</Typography>
                <Box sx={{ '& p': { m: 0 }, color: 'text.secondary', fontSize: '0.9rem', maxHeight: 300, overflow: 'auto' }}>
                  <Markdown>{created.prompt}</Markdown>
                </Box>
              </Paper>
            </Box>
          </Box>
        )}
      </CardContent>
    </Card>
  )
}
