import '@testing-library/jest-dom/vitest'
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Onboard from './Onboard'

const mocks = vi.hoisted(() => ({
  startSession: vi.fn(),
  sendMessageToSession: vi.fn(),
  finalizeSession: vi.fn(),
  uploadAudio: vi.fn(),
}))

vi.mock('../api', () => ({
  api: {
    uploadAudio: mocks.uploadAudio,
    startSession: mocks.startSession,
    sendMessageToSession: mocks.sendMessageToSession,
    finalizeSession: mocks.finalizeSession,
  },
}))

// Mock speech SDK hook to avoid accessing real media devices
vi.mock('../hooks/useSpeechSDK', () => ({
  useSpeechSDK: () => ({
    startRecognition: vi.fn(),
    stopRecognition: vi.fn(),
    isRecording: false,
    ready: false,
  }),
}))

describe('Onboard manual text guided flow', () => {
  it('runs multi-turn from uploaded audio seed and finalizes', async () => {
    mocks.uploadAudio.mockResolvedValue({ transcript: 'seed text' })
    mocks.startSession.mockResolvedValue({
      session: {
        session_id: 's1',
        user_id: 'demo-user',
        created_at: Date.now() / 1000,
        fields: {},
        missing: ['brand'],
        history: [],
      },
      reply: '欢迎来到向导',
    })

    mocks.sendMessageToSession.mockResolvedValue({
      session: {
        session_id: 's1',
        user_id: 'demo-user',
        created_at: Date.now() / 1000,
        fields: { brand: 'test brand' },
        missing: [],
        history: [
          { role: 'user', text: 'hi' },
          { role: 'assistant', text: '收集完成' },
        ],
      },
      reply: '收集完成',
      done: true,
    })

    mocks.finalizeSession.mockResolvedValue({
      agent_id: 'agent-123',
      prompt: 'mock prompt content',
      profile: { brand: 'test brand' },
      has_voice_template: false,
    })

    render(
      <MemoryRouter>
        <Onboard />
      </MemoryRouter>
    )

    const fileInput = screen.getAllByLabelText(/上传音频文件（长音频支持）/i)[0]
    const file = new File(['dummy'], 'test.wav', { type: 'audio/wav' })
    fireEvent.change(fileInput, { target: { files: [file] } })

    fireEvent.click(screen.getByRole('button', { name: /用语音开启向导/i }))

    await waitFor(() => expect(mocks.uploadAudio).toHaveBeenCalled())
    await waitFor(() => expect(mocks.startSession).toHaveBeenCalledWith('seed text'))
    expect(await screen.findByText(/欢迎来到向导/i)).toBeInTheDocument()

    const input = screen.getByPlaceholderText(/输入你的补充信息/i)
    fireEvent.change(input, { target: { value: 'hi' } })
    fireEvent.click(screen.getByRole('button', { name: /发送/i }))
    await waitFor(() => expect(mocks.sendMessageToSession).toHaveBeenCalledWith('s1', 'hi'))

    fireEvent.click(screen.getByRole('button', { name: /确认生成/i }))
    await waitFor(() => expect(mocks.finalizeSession).toHaveBeenCalledWith('s1'))

    expect(await screen.findByText(/mock prompt content/i)).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: /前往聊天测试/i })).toBeInTheDocument()
  })
})
