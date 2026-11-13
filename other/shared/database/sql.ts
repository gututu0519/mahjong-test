// SQL compatibility at the persistence boundary. Monetary values remain integer
// minor units. This is deliberately limited to the repository's audited dialect.
export const quote = (name: string) => '"' + name.replaceAll('"', '""') + '"';
export function splitSQL(sql: string): string[] {
  const result: string[] = []; let part = '', quoted = false, comment = false;
  for (let i = 0; i < sql.length; i++) {
    const c = sql[i];
    if (comment) { if (c === '\n') comment = false; else continue; }
    if (!quoted && c === '-' && sql[i + 1] === '-') { comment = true; i++; continue; }
    if (c === "'") {
      part += c;
      if (quoted && sql[i + 1] === "'") {part += sql[++i]; continue;}
      quoted = !quoted; continue;
    }
    if (c === ';' && !quoted) { if(part.trim()) result.push(part.trim()); part = ''; }
    else part += c;
  }
  if(part.trim()) result.push(part.trim());
  return result;
}
export function dialect(sql: string): string {
  return sql
    .replace(/json_extract\(\s*([\w.]+)\s*,\s*'\$\.([\w.]+)'\s*\)/gi, (_all, column, path) => {
      const expression = `(${column}::jsonb #>> '{${path.replaceAll('.', ',')}}')`;
      return ['game_id', 'timestamp', 'wallet_debit_minor'].includes(path) ? `(${expression}::bigint)` : expression;
    })
    .replace(/\bunixepoch\(\)/gi, '(extract(epoch FROM clock_timestamp())::bigint)')
    .replace(/\bAS INTEGER\b/gi, 'AS BIGINT')
    .replace(/\bGLOB 'GTT\[0-9\]\[0-9\]\[0-9\]\[0-9\]\[0-9\]\[0-9\]'/gi, () => "~ '^GTT[0-9]{6}$'")
    .replace(/strftime\('%Y-%m-%d',\s*([\w.]+),\s*'unixepoch'\)/gi, "to_char(to_timestamp($1) AT TIME ZONE 'UTC','YYYY-MM-DD')")
    .replace(/\bBEGIN IMMEDIATE\b/gi, 'BEGIN');
}
export function placeholders(sql: string, args: any[]) {
  let quoted = false, n = 0, out = '';
  for(let i=0;i<sql.length;i++) {
    const c=sql[i];
    if(c==="'") {out+=c;if(quoted&&sql[i+1]==="'"){out+=sql[++i];continue;}quoted=!quoted;}
    else if(c==='?'&&!quoted) {
      n++; const value=args[n-1];
      out+='$'+n+(typeof value==='number'?(Number.isInteger(value)?'::bigint':'::double precision'):typeof value==='boolean'?'::bigint':'');
    } else out+=c;
  }
  if(n!==args.length) throw Error(`SQL parameter count mismatch: expected ${n}, received ${args.length}`);
  return out;
}
