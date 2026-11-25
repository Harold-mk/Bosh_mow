import { useParams, useSearchParams } from 'react-router'
import { Reader } from './Reader.tsx'

/** Lecteur as a page: from a subject or a chapter, opened at ?page= (1 by default). */
export function ReaderScreen() {
  const { resourceId } = useParams()
  const [search] = useSearchParams()
  const page = Number(search.get('page')) || 1
  return <Reader key={resourceId} resourceId={Number(resourceId)} page={page} />
}
