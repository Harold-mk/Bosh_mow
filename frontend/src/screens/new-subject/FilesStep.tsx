import { useRef, useState, type DragEvent } from 'react'
import { addFile, deleteFile, messageOf, type Resource } from '../../api.ts'
import { Icon } from '../../components/Icon.tsx'
import { Notice } from '../../components/Notice.tsx'
import { fileSummary } from '../../format.ts'

const ACCEPT = '.pdf,.md,.markdown'

/** A file of the list: being read, imported, or refused with the reason. */
type Row =
  | { key: number; name: string; status: 'busy' }
  | { key: number; name: string; status: 'done'; resource: Resource }
  | { key: number; name: string; status: 'error'; error: string }

type Props = {
  subjectId: number
  files: Resource[] // the files already imported
  onAdded: (file: Resource) => void
  onRemoved: (fileId: number) => void
  onNext: () => void
  onBack: () => void
}

/** Documents: files are dropped or chosen, then read one after the other. */
export function FilesStep({ subjectId, files, onAdded, onRemoved, onNext, onBack }: Props) {
  const [rows, setRows] = useState<Row[]>(() =>
    files.map((resource) => ({
      key: resource.id,
      name: resource.file_name,
      status: 'done',
      resource,
    })),
  )
  const nextKey = useRef(-1) // negative: never the id of an imported file
  const input = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const [error, setError] = useState<string>()

  const busy = rows.some((row) => row.status === 'busy')
  const imported = rows.some((row) => row.status === 'done')

  function replace(key: number, row: Row) {
    setRows((current) => current.map((candidate) => (candidate.key === key ? row : candidate)))
  }

  async function upload(chosen: File[]) {
    const added = chosen.map((file) => ({ key: nextKey.current--, file }))
    setRows((current) => [
      ...current,
      ...added.map(({ key, file }): Row => ({ key, name: file.name, status: 'busy' })),
    ])
    for (const { key, file } of added) {
      try {
        const resource = await addFile(subjectId, file)
        replace(key, { key, name: file.name, status: 'done', resource })
        onAdded(resource)
      } catch (reason) {
        replace(key, { key, name: file.name, status: 'error', error: messageOf(reason) })
      }
    }
  }

  async function remove(row: Row) {
    setError(undefined)
    if (row.status === 'done') {
      try {
        await deleteFile(subjectId, row.resource.id)
        onRemoved(row.resource.id)
      } catch (reason) {
        setError(messageOf(reason))
        return
      }
    }
    setRows((current) => current.filter((candidate) => candidate.key !== row.key))
  }

  function drop(event: DragEvent) {
    event.preventDefault()
    setDragging(false)
    upload([...event.dataTransfer.files])
  }

  return (
    <div
      className="wizard-step"
      onDragOver={(event) => {
        event.preventDefault()
        setDragging(true)
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={drop}
    >
      <input
        ref={input}
        type="file"
        multiple
        accept={ACCEPT}
        hidden
        onChange={(event) => {
          upload([...(event.target.files ?? [])])
          event.target.value = '' // the same file can be chosen again
        }}
      />
      {rows.length === 0 ? (
        <button
          type="button"
          className={dragging ? 'dropzone dragging' : 'dropzone'}
          onClick={() => input.current?.click()}
        >
          <Icon name="upload" />
          <strong>Glisse tes fichiers ici</strong>
          <span className="hint">
            Livres en PDF et notes en Markdown. Clique pour choisir des fichiers.
          </span>
        </button>
      ) : (
        <div className={dragging ? 'files dragging' : 'files'}>
          {rows.map((row) => (
            <div className="file-row" key={row.key}>
              <Icon name="file" />
              <span className="file-name">
                <strong>{row.name}</strong>
                <span className="hint">
                  {row.status === 'done' && fileSummary(row.resource)}
                  {row.status === 'error' && row.error}
                </span>
              </span>
              <span className="file-state">
                {row.status === 'busy' && (
                  <>
                    <span className="hint">Analyse</span>
                    <span className="analysis-dots" aria-hidden="true">
                      {Array.from({ length: 10 }, (_, k) => (
                        <span key={k} />
                      ))}
                    </span>
                  </>
                )}
                {row.status === 'done' && (
                  <>
                    <Icon name="check" />
                    Analysé
                  </>
                )}
                {row.status === 'error' && <span className="hint">Refusé</span>}
              </span>
              <button
                type="button"
                className="icon-button"
                aria-label={`Retirer ${row.name}`}
                title="Retirer"
                disabled={row.status === 'busy'}
                onClick={() => remove(row)}
              >
                <Icon name="close" />
              </button>
            </div>
          ))}
          <button
            type="button"
            className="button ghost files-add"
            onClick={() => input.current?.click()}
          >
            <Icon name="plus" size={16} />
            Ajouter des fichiers
          </button>
        </div>
      )}
      {error && <Notice>{error}</Notice>}
      <div className="actions wizard-actions">
        <button
          type="button"
          className="button primary"
          disabled={!imported || busy}
          onClick={onNext}
        >
          Voir la proposition
        </button>
        <button type="button" className="button ghost" onClick={onBack}>
          Retour
        </button>
        {busy && <span className="hint">Analyse des fichiers en cours…</span>}
      </div>
    </div>
  )
}
