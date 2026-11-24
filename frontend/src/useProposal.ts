import { useCallback, useEffect, useState } from 'react'
import {
  askProposal,
  getProposal,
  messageOf,
  type Proposal,
  type ProposalState,
  type Resource,
} from './api.ts'

const FOLLOW_MS = 3000 // how often to ask where a proposal stands while Claude works

/** Follow Claude's proposal for a subject, asking again every few seconds while it is
 *  pending or running. `state` is undefined while loading, null if none was asked for;
 *  `ask` asks for a new proposal, or tries again at once one that waits for Claude. */
export function useProposal(subjectId: number) {
  const [state, setState] = useState<ProposalState | null>()
  const [error, setError] = useState<string>()
  const [request, setRequest] = useState(0) // a new request restarts the follow-up

  useEffect(() => {
    let stopped = false
    let timer = 0
    async function follow() {
      try {
        const current = await getProposal(subjectId)
        if (stopped) return
        setState(current)
        setError(undefined)
        if (current?.status === 'pending' || current?.status === 'running') {
          timer = window.setTimeout(follow, FOLLOW_MS)
        }
      } catch (reason) {
        if (!stopped) setError(messageOf(reason))
      }
    }
    follow()
    return () => {
      stopped = true
      window.clearTimeout(timer)
    }
  }, [subjectId, request])

  const ask = useCallback(async () => {
    try {
      setState(await askProposal(subjectId))
      setError(undefined)
      setRequest((n) => n + 1)
    } catch (reason) {
      setError(messageOf(reason))
    }
  }, [subjectId])

  return { state, error, ask }
}

/** The files of a subject as a key, which changes when a file is added or removed. */
export function filesKey(files: Resource[]): string {
  return idsKey(files.map((file) => file.id))
}

/** Whether a proposal splits exactly these files: it covers all the files of its time. */
export function splitsFiles(proposal: Proposal, files: Resource[]): boolean {
  const ids = proposal.chapters.flatMap((chapter) =>
    chapter.sources.map((source) => source.resource_id),
  )
  return idsKey([...new Set(ids)]) === filesKey(files)
}

function idsKey(ids: number[]): string {
  return [...ids].sort((a, b) => a - b).join(',')
}
