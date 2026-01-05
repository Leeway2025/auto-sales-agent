import '@testing-library/jest-dom/vitest'
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import OnboardSession from './OnboardSession'

const mocks = vi.hoisted(() => ({
  startSession: vi.fn(),
  sendMessageToSession: vi.fn(),
  finalizeSession: vi.fn(),
  uploadVoiceTemplate: vi.fn(),
}))

vi.mock('../api', () => ({
  api: {
    startSession: mocks.startSession,
    sendMessageToSession: mocks.sendMessageToSession,
    finalizeSession: mocks.finalizeSession,
    uploadVoiceTemplate: mocks.uploadVoiceTemplate,
  },
}))

describe('OnboardSession multi-turn flow', () => {
  it('runs start -> user send -> finalize', async () => {
    mocks.startSession.mockResolvedValue({
      session: {
        session_id: 's1',
        user_id: 'demo-user',
        created_at: Date.now() / 1000,
        fields: {},
        missing: ['brand'],
        history: [],
      },
      reply: '你好，我是向导',
    })

    mocks.sendMessageToSession.mockResolvedValue({
      session: {
        session_id: 's1',
        user_id: 'demo-user',
        created_at: Date.now() / 1000,
        fields: { brand: 'test brand' },
        missing: [],
        history: [
          { role: 'user', text: 'test message' },
          { role: 'assistant', text: '收集完成 [DONE]' },
        ],
      },
      reply: '收集完成 [DONE]',
      done: true,
    })

    mocks.finalizeSession.mockResolvedValue({
      agent_id: 'asst_test',
      prompt: 'prompt-md',
      profile: { brand: 'test brand' },
      has_voice_template: false,
    })

    render(
      <MemoryRouter>
        <OnboardSession />
      </MemoryRouter>
    )

    fireEvent.click(screen.getByRole('button', { name: /开始向导/i }))

    await waitFor(() => expect(mocks.startSession).toHaveBeenCalled())
    expect(await screen.findByText(/你好，我是向导/i)).toBeInTheDocument()

    const input = screen.getByPlaceholderText(/输入你的补充信息/i)
    fireEvent.change(input, { target: { value: 'test message' } })
    fireEvent.click(screen.getByRole('button', { name: /发送/i }))

    await waitFor(() => expect(mocks.sendMessageToSession).toHaveBeenCalledWith('s1', 'test message'))
    expect(await screen.findByText(/收集完成 \[DONE]/i)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /确认生成/i }))
    await waitFor(() => expect(mocks.finalizeSession).toHaveBeenCalledWith('s1'))
    expect(await screen.findByText(/Agent 已创建成功/i)).toBeInTheDocument()
    expect(await screen.findByText(/asst_test/i)).toBeInTheDocument()
  })
})
