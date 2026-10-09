'use strict';

// World text is data: no HTML insertion, source evaluation, or generated URLs.
const $ = id => document.getElementById(id);
const themeRoot = document.querySelector(':root');
const themePreference = $('theme-preference');
themePreference.value = ['light', 'dark'].includes(themeRoot.dataset.theme) ? themeRoot.dataset.theme : 'system';
themePreference.addEventListener('change', () => {
  const preference = ['light', 'dark'].includes(themePreference.value) ? themePreference.value : 'system';
  themePreference.value = preference;
  themeRoot.dataset.theme = preference;
  try {
    if (preference === 'system') localStorage.removeItem('delvetalk.theme');
    else localStorage.setItem('delvetalk.theme', preference);
  } catch { /* The selected palette still applies for this page. */ }
});

const state = { world: null, card: null, draft: null, preparation: null, preparationGeneration: 0, detail: null, generation: 0, routeGeneration: 0, location: location.href, sending: false, uncertain: false };
const authoring = { draft: null, pending: false, preparing: false, uncertain: false, source: null, sourceText: null, rawFiles: {}, status: null };
const agentSession = { token: '', me: null, surface: 'studio', generation: 0, readGeneration: 0, prepareGeneration: 0, card: null, conversation: null, conversations: new Map(), proposal: null, sending: false, uncertain: false, challenge: null, proof: null };
const text = value => typeof value === 'string' ? value : value == null ? '' : JSON.stringify(value);
function element(tag, className, content) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (content !== undefined) node.textContent = text(content);
  return node;
}
const preparationAnswers = element('div', 'preparation-answers');
$('draft-panel').append(preparationAnswers);
function notice(message, error = false) {
  $('notice').textContent = text(message);
  $('notice').classList.toggle('error', error);
  $('notice').hidden = !message;
}
async function api(path, body) {
  const options = { headers: { Accept: 'application/json' }, credentials: 'same-origin' };
  if (body !== undefined) {
    options.method = 'POST';
    options.headers['Content-Type'] = 'application/json';
    options.headers['X-Delvetalk-CSRF'] = state.world?.csrf || '';
    options.body = JSON.stringify(body);
  }
  const response = await fetch(path, options);
  let data;
  try { data = await response.json(); }
  catch { throw new Error(`The portal returned an unreadable reply (${response.status}).`); }
  if (!response.ok) {
    const error = new Error(text(data.message || data.error) || `Request failed (${response.status}).`);
    error.code = data.error;
    error.httpStatus = response.status;
    throw error;
  }
  return data;
}
async function busy(button, label, work) {
  const before = button.textContent;
  button.disabled = true;
  button.textContent = label;
  try { await work(); }
  catch (error) { notice(error.message, true); }
  finally { button.disabled = false; button.textContent = before; }
}
async function copy(value, button) {
  try {
    if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(value);
    else {
      const area = element('textarea', 'copy-buffer');
      area.value = value;
      area.setAttribute('aria-label', 'Text to copy');
      document.body.append(area);
      area.select();
      const copied = document.execCommand('copy');
      area.remove();
      if (!copied) throw new Error('Copy is unavailable. Select the command text to copy it.');
    }
    const prior = button.textContent;
    button.textContent = 'Copied';
    setTimeout(() => { if (button.isConnected) button.textContent = prior; }, 1600);
  } catch (error) { notice(error.message, true); }
}
function renderObjects() {
  $('objects').replaceChildren();
  for (const object of state.world.objects || []) {
    const button = element('button', 'object-link');
    button.type = 'button';
    button.setAttribute('aria-current', String(object.id === state.card?.object));
    const symbol = element('span', 'object-symbol', '◇');
    symbol.setAttribute('aria-hidden', 'true');
    const label = element('span');
    label.append(element('strong', '', object.title || object.id));
    label.append(element('small', '', object.title && object.title !== object.id ? object.id
      : object.version == null ? 'Open object' : `Version ${text(object.version)}`));
    button.append(symbol, label);
    button.addEventListener('click', () => openObject(object.id, true, 'main', 'push'));
    $('objects').append(button);
  }
  if (!$('objects').childElementCount) $('objects').append(element('p', 'muted', 'No objects here yet.'));
  if (state.world.next) {
    const next = element('button', 'secondary', 'Next page');
    next.type = 'button';
    next.addEventListener('click', () => busy(next, 'Reading…', async () => {
      try { await loadWorld(state.world.next); }
      catch (error) { throw new Error(`${error.message} Refresh the object shelf to start a new listing.`); }
    }));
    $('objects').append(next);
  }
}
async function loadWorld(path = '/api/world') {
  const generation = state.catalogueGeneration = (state.catalogueGeneration || 0) + 1;
  const world = await api(path);
  if (generation !== state.catalogueGeneration) return state.world;
  state.world = world;
  $('agent-session').hidden = world.agents?.available === false;
  $('world-title').textContent = world.title || 'The workbench';
  const preview = world.mode === 'public-preview';
  $('mode').textContent = preview ? 'Public preview' : world.mode === 'local-interactive' ? 'Local world' : 'Read-only world';
  $('principal').textContent = world.principal ? `As ${world.principal}` : '';
  document.querySelector('.connection').classList.add('ready');
  $('footer-mode').textContent = preview ? 'Temporary previews · copy what you want to keep.' : world.mode === 'local-interactive'
    ? 'Every action begins as a draft.' : 'Explore, inspect and prepare a draft.';
  $('preview-scope').hidden = !preview;
  const minutes = Math.ceil((world.custody?.ttlSeconds || 900) / 60);
  $('preview-scope').textContent = `Explore this world and preview its offered actions. Nothing you do here changes the world or posts to town. Previews last up to ${minutes} minutes; copy a summary to keep your idea. Exact request data is available separately.`;
  $('repository-export').hidden = preview || world.capabilities?.repository === false;
  const assisted = world.interpretation === 'model-assisted';
  $('interpret-label').textContent = assisted ? 'Or say what you have in mind' : 'Or paste an action token';
  $('intent-text').placeholder = assisted ? 'Describe a next step…' : 'do CARD ACTION';
  $('interpret-form').hidden = preview;
  $('interpret-help').textContent = assisted
    ? 'A suggestion is a draft. You decide whether to send it.'
    : 'Copied tokens become proposals here. You decide whether to send them.';
  renderObjects();
  configureAuthoring(world.authoring);
  if (agentSession.me) updateAgentWorkspace();
  return world;
}
function clearRepositoryRecord() {
  $('repository-record').hidden = true;
  $('repository-json').textContent = '';
  $('repository-status').textContent = '';
}
function writeLocation(url, push = false) {
  history[push ? 'pushState' : 'replaceState'](null, '', url);
  state.location = String(url);
}
function clearDraft(updateUrl = true) {
  if (updateUrl) ++state.preparationGeneration;
  state.draft = null;
  state.preparation = null;
  preparationAnswers.replaceChildren();
  state.uncertain = false;
  clearRepositoryRecord();
  $('draft-panel').hidden = true;
  $('draft-state').textContent = '';
  if (!updateUrl) return;
  const url = new URL(location.href);
  url.searchParams.delete('draft');
  url.searchParams.delete('preparation');
  writeLocation(url);
}
async function openObject(id, focus = false, panel = 'main', navigation = 'replace', childSelection = null, retainedCard = null) {
  if (state.sending) return notice('Wait for the send result before replacing this reading.');
  const generation = ++state.generation;
  ++state.routeGeneration;
  notice('');
  try {
    let card;
    if (retainedCard) {
      card = await api(`/api/card?card=${encodeURIComponent(retainedCard)}`);
      id = card.object;
    } else if (childSelection) {
      const result = await api(`/api/child?card=${encodeURIComponent(childSelection.card)}&key=${encodeURIComponent(childSelection.key)}`);
      if (result.status !== 'opened') throw new Error(result.message || 'This child is unavailable.');
      card = result.card;
      id = card.object;
    } else card = await api(`/api/object?object=${encodeURIComponent(id)}&panel=${encodeURIComponent(panel)}`);
    if (generation !== state.generation || state.sending || authoring.pending) return;
    state.card = card;
    state.detail = null;
    if (!state.uncertain) clearDraft(false);
    $('object-title').textContent = card.title || id;
    $('object-prose').textContent = text(card.prose);
    $('version').textContent = card.version == null ? '' : `v${text(card.version)}`;
    $('card-token').textContent = card.card;
    $('object-meta').hidden = false;
    $('inspect').hidden = false;
    $('inspect').open = false;
    $('detail-content').textContent = 'Opening…';
    $('copy-detail').disabled = true;
    $('detail-tabs').replaceChildren();
    $('copy-reference').hidden = !card.objectRef;
    $('reference-status').textContent = text(card.referenceStatus);
    $('reference-status').hidden = !card.referenceStatus;
    $('unsupported-status').textContent = text(card.unsupported);
    $('unsupported-status').hidden = !card.unsupported;
    $('interpret-form').hidden = state.world.mode === 'public-preview';
    $('intent-text').value = '';
    $('interpret-result').replaceChildren();
    renderPanels(card);
    renderActions(card);
    if (card.panel === 'main') {
      const listed = state.world.objects.find(object => object.id === id);
      if (listed && card.title) listed.title = card.title;
    }
    renderViewChildren(card);
    $('object-children').replaceChildren();
    $('object-children').hidden = true;
    renderObjects();
    const url = new URL(location.href);
    url.searchParams.set('object', id);
    if (card.panel && card.panel !== 'main') url.searchParams.set('panel', card.panel);
    else url.searchParams.delete('panel');
    if (state.uncertain && state.draft) url.searchParams.set('draft', state.draft.draft);
    else url.searchParams.delete('draft');
    url.searchParams.delete('preparation');
    writeLocation(url, navigation === 'push');
    document.title = `${card.title || id} · DelveTalk`;
    if (focus) $('object-card').focus({ preventScroll: true });
    return true;
  } catch (error) {
    if (generation === state.generation) notice(childSelection
      ? `Unavailable: ${childSelection.label}. ${error.message}` : error.message, true);
  }
}
function renderPanels(card) {
  const nav = $('object-panels');
  nav.replaceChildren();
  const panels = card.panels || [{ id: 'main', label: 'Overview' }];
  nav.hidden = panels.length < 2;
  for (const panel of panels) {
    const button = element('button', 'panel-link', panel.label);
    button.type = 'button';
    button.setAttribute('aria-current', String(panel.id === (card.panel || 'main')));
    button.addEventListener('click', () => openObject(card.object, false, panel.id, 'push'));
    nav.append(button);
  }
  $('panel-warning').textContent = card.panelWarning || '';
  $('panel-warning').hidden = !card.panelWarning;
}
function fieldInput(field, actionId, index, partial = false) {
  const label = element('label', 'field-label');
  const id = `field-${actionId}-${index}`;
  label.htmlFor = id;
  const caption = element('span', '', field.label || field.name);
  if (field.required && !partial) caption.append(element('span', 'required', ' · required'));
  let input;
  if (field.type === 'enum' || (field.type === 'bool' && partial)) {
    input = element('select');
    const empty = element('option', '', 'Choose…');
    empty.value = '';
    input.append(empty);
    for (const [optionIndex, option] of (field.type === 'bool' ? ['Yes', 'No'] : field.options || []).entries()) {
      const choice = element('option', '', option);
      choice.value = field.type === 'bool' ? String(optionIndex === 0) : String(optionIndex);
      input.append(choice);
    }
  } else {
    const longText = field.type === 'string' && field.maxLength > 256;
    input = element(longText ? 'textarea' : 'input');
    if (longText) input.rows = 6;
    else input.type = field.type === 'bool' ? 'checkbox' : 'text';
    if (field.type === 'nat') {
      input.inputMode = 'numeric';
      input.pattern = '0|[1-9][0-9]*';
      const minimum = Number.isSafeInteger(field.minimum) ? field.minimum : 0;
      const maximum = Number.isSafeInteger(field.maximum) ? field.maximum : Number.MAX_SAFE_INTEGER;
      input.title = `A whole number from ${minimum} to ${maximum}`;
      input.placeholder = `${minimum}–${maximum}`;
    }
    if (field.placeholder) input.placeholder = field.placeholder;
  }
  input.id = id;
  input.name = field.name;
  input.required = !partial && Boolean(field.required) && (field.type === 'enum' || field.type === 'nat'
    || (field.type === 'string' && field.minLength > 0));
  input.dataset.fieldType = field.type;
  if (field.type === 'bool' && !partial) label.append(input, caption);
  else label.append(caption, input);
  if (Object.hasOwn(field, 'example')) {
    // An authored example is guidance, never a default or a bound input.
    const example = field.example === '' ? '""' : text(field.example);
    if (field.type === 'string' || field.type === 'nat') input.placeholder = example;
    const hint = element('span', 'help', `Example: ${example}`);
    hint.id = `${id}-example`;
    input.setAttribute('aria-describedby', hint.id);
    label.append(hint);
  }
  return { label, input, field, partial };
}
function readFields(controls) {
  const fields = Object.create(null);
  for (const { field, input, partial } of controls) {
    input.setCustomValidity('');
    if (partial && input.value === '') continue;
    if (field.type === 'bool') {
      if (partial && !['true', 'false'].includes(input.value)) throw new Error('Choose Yes or No.');
      fields[field.name] = partial ? input.value === 'true' : input.checked;
    }
    else if (!input.value && !field.required) continue;
    else if (field.type === 'enum') {
      if (input.value === '') {
        input.setCustomValidity('Choose one of the offered values.');
        input.reportValidity();
        throw new Error('Choose a value in the action form.');
      }
      fields[field.name] = field.options[Number(input.value)];
    }
    else if (field.type === 'nat') {
      const value = Number(input.value);
      const minimum = Number.isSafeInteger(field.minimum) ? field.minimum : 0;
      const maximum = Number.isSafeInteger(field.maximum) ? field.maximum : Number.MAX_SAFE_INTEGER;
      if (!/^(0|[1-9][0-9]*)$/.test(input.value) || !Number.isSafeInteger(value) || value < minimum || value > maximum) {
        input.setCustomValidity(`Enter a whole number from ${minimum} to ${maximum}.`);
        input.reportValidity();
        throw new Error('Check the number in the action form.');
      }
      fields[field.name] = value;
    } else {
      if (field.type === 'string') {
        const length = [...input.value].length;
        if ((field.minLength != null && length < field.minLength) || (field.maxLength != null && length > field.maxLength)) {
          input.setCustomValidity(`Enter between ${field.minLength ?? 0} and ${field.maxLength ?? 'the permitted number of'} characters.`);
          input.reportValidity();
          throw new Error('Check the text length in the action form.');
        }
      }
      fields[field.name] = input.value;
    }
  }
  return fields;
}
function renderActions(card) {
  const actions = Array.isArray(card.actions) ? card.actions : [];
  $('actions').replaceChildren();
  $('actions-section').hidden = false;
  for (const [index, action] of actions.entries()) {
    const form = element('form', 'action');
    form.dataset.actionId = action.id;
    const top = element('div', 'action-top');
    const label = element('p', 'action-label', action.label || action.id);
    const submit = element('button', 'secondary', state.world?.mode === 'public-preview' ? 'Preview' : 'Prepare');
    submit.type = 'submit';
    const inspectOnly = action.inspectOnly === true || action.available === false;
    submit.disabled = inspectOnly;
    top.append(label, submit);
    form.append(top);
    if (action.description) form.append(element('p', 'action-description', action.description));
    if (action.children?.length) {
      const preview = element('p', 'help');
      preview.textContent = `Creates new objects from ${action.children.map(child => child.value ?? child.field).join(', ')}. Each name must still be absent when the world admits the action.`;
      form.append(preview);
    }
    if (action.observedAvailable === false)
      form.append(element('p', 'help', 'Its condition was false when this room was read. The world checks it again when you send.'));
    const controls = (action.fields || []).map((field, i) => fieldInput(field, index, i, action.preparation === true));
    form.documentControls = controls;
    if (action.preparation) form.append(element('p', 'help', 'Start with what you know. The object can ask for more before proposing an action.'));
    for (const control of controls) {
      if (action.children?.some(child => child.field === control.field.name)) {
        control.input.pattern = '[A-Za-z0-9_-]{1,64}';
        control.input.title = 'A new child name using letters, digits, underscores or hyphens';
      }
    }
    if (controls.length) {
      const group = element('div', 'action-fields');
      controls.forEach(control => group.append(control.label));
      form.append(group);
    }
    if (inspectOnly) form.append(element('p', 'help', action.reason || 'Inspect this action’s contract for its required input.'));
    const tokenRow = element('div', 'action-token');
    const code = element('code', '', action.token || `do ${card.card} ${action.id}`);
    const copyButton = element('button', 'text-button', 'Copy token');
    copyButton.type = 'button';
    copyButton.addEventListener('click', async () => {
      try {
        const fields = readFields(controls);
        if (controls.length && !form.reportValidity()) return;
        const command = `do ${card.card} ${action.id}${Object.keys(fields).length ? ` ${JSON.stringify(fields)}` : ''}`;
        await copy(command, copyButton);
      } catch (error) { notice(error.message, true); }
    });
    tokenRow.append(code, copyButton);
    if (state.world?.mode !== 'public-preview') form.append(tokenRow);
    controls.forEach(({ input }) => input.addEventListener('input', () => input.setCustomValidity('')));
    form.addEventListener('submit', event => {
      event.preventDefault();
      busy(submit, 'Preparing…', async () => {
        const fields = readFields(controls);
        if (!form.reportValidity()) return;
        await prepare(card.card, action.id, fields);
      });
    });
    $('actions').append(form);
  }
  if (!actions.length) $('actions').append(element('p', 'muted', 'No actions are offered in this reading.'));
  const rendered = renderLivingDocument(card, $('object-document'), $('actions'), {
    reference: node => openObject(node.object, true, node.panel, 'push', { card: card.card, key: node.childKey }),
  });
  $('object-prose').hidden = rendered;
  $('actions-section').hidden = rendered && !$('actions').childElementCount;
}
function documentValue(value) {
  if (value && typeof value === 'object') {
    const kind = value.variant || value.kind || value.label;
    const payload = value.payload || value;
    if (['text', 'nat', 'bool', 'natural', 'boolean', 'label'].includes(kind)
        && ['string', 'boolean', 'number'].includes(typeof payload.value)) return payload.value;
  }
  return value;
}
// This is a renderer for the source-defined Document ABI. Only qualified
// actionId/childKey bindings from the captured card create controls or links.
function renderLivingDocument(card, target, forms, context = {}) {
  target.replaceChildren();
  target.hidden = !card.document;
  if (!card.document) return false;
  const actionForms = new Map([...forms.children].filter(form => form.dataset?.actionId).map(form => [form.dataset.actionId, form]));
  const actions = new Map((card.actions || []).map(action => [action.id, action]));
  const used = new Set();
  let remaining = 1024;
  let collectRemaining = 1024;
  const bindings = new Map();
  function collect(node, depth = 0) {
    if (!node || --collectRemaining < 0 || depth > 64) return;
    if (node.kind === 'fields' && node.actionId && actions.has(node.actionId)) bindings.set(node.actionId, node);
    if (node.kind === 'sequence') for (const child of (node.items || []).slice(0, 1024)) collect(child, depth + 1);
    if (node.kind === 'quote' || node.kind === 'result') collect(node.body, depth + 1);
  }
  collect(card.document);
  function offer(actionId, label) {
    const form = actionForms.get(actionId);
    if (!form) return element('p', 'document-unbound', label || 'This offer is available for inspection.');
    if (used.has(actionId)) {
      const link = element('button', 'document-reference', label || actions.get(actionId).label);
      link.type = 'button';
      link.addEventListener('click', () => { form.scrollIntoView({ block: 'nearest', behavior: 'smooth' }); form.documentControls?.[0]?.input.focus(); });
      return link;
    }
    used.add(actionId);
    const values = bindings.get(actionId)?.values || [];
    for (const { name, value } of values) {
      const control = form.documentControls?.find(control => control.field.name === name);
      const plain = documentValue(value);
      if (!control) continue;
      if (control.field.type === 'bool' && typeof plain === 'boolean') control.input.checked = plain;
      else if (control.field.type === 'string' && typeof plain === 'string') control.input.value = plain;
      else if (control.field.type === 'enum' && control.field.options.includes(plain)) control.input.value = String(control.field.options.indexOf(plain));
      else if (control.field.type === 'nat' && (typeof plain === 'string' || Number.isSafeInteger(plain)) && /^(0|[1-9][0-9]*)$/.test(String(plain)) && Number.isSafeInteger(Number(plain))) control.input.value = String(plain);
    }
    if (form.parentNode) form.parentNode.removeChild(form);
    form.classList.add('document-offer');
    return form;
  }
  function node(value, depth = 0) {
    if (!value || typeof value !== 'object' || --remaining < 0 || depth > 64) return element('p', 'help', 'This part is too large to display here. Its source remains available for inspection.');
    switch (value.kind) {
      case 'text': return element('p', 'document-text', value.value);
      case 'sequence': {
        const sequence = element('div', 'document-sequence');
        for (const child of (value.items || []).slice(0, 1024)) sequence.append(node(child, depth + 1));
        return sequence;
      }
      case 'quote': {
        const quote = element('blockquote', 'document-quote');
        quote.append(node(value.body, depth + 1));
        if (value.attribution) quote.append(element('footer', '', value.attribution));
        return quote;
      }
      case 'reference': {
        if (!value.childKey || typeof context.reference !== 'function') return element('span', 'document-unbound-reference', value.label);
        const button = element('button', 'document-reference', value.label);
        button.type = 'button';
        button.addEventListener('click', () => busy(button, 'Opening…', () => context.reference(value)));
        return button;
      }
      case 'offer': return offer(value.actionId, value.label);
      case 'fields': {
        const group = element('section', 'document-bindings');
        if (value.values?.length) {
          const list = element('dl', 'draft-fields');
          for (const field of value.values) list.append(element('dt', '', field.name), element('dd', '', text(documentValue(field.value))));
          group.append(list);
        }
        if (value.needs?.length) group.append(element('p', 'help', `Still open: ${value.needs.join(', ')}`));
        if (value.actionId && !used.has(value.actionId)) group.append(offer(value.actionId));
        return group;
      }
      case 'source': {
        const source = element('details', 'document-source');
        source.append(element('summary', '', value.language ? `${value.language} source` : 'Source'));
        const code = element('pre', '', value.code);
        code.tabIndex = 0;
        const button = element('button', 'text-button', 'Copy source');
        button.type = 'button';
        button.addEventListener('click', () => copy(value.code, button));
        source.append(button, code);
        if (value.revision) source.append(element('p', 'help', `Revision: ${value.revision}`));
        return source;
      }
      case 'result': {
        const result = element('section', 'document-result');
        result.dataset.status = ['pending', 'refused', 'uncertain', 'committed', 'complete'].includes(value.status) ? value.status : 'recorded';
        result.append(element('p', 'document-status', value.status), node(value.body, depth + 1));
        return result;
      }
      case 'continuation': {
        const section = element('details', 'document-continuation');
        section.append(element('summary', '', value.label || 'Continuation'));
        section.append(element('p', 'help', 'A retained continuation. No receiving control is attached to this reading.'));
        section.append(element('pre', '', JSON.stringify({ key: value.key, after: value.after, limit: value.limit }, null, 2)));
        return section;
      }
      default: return element('p', 'help', 'This document section is not supported by this viewer. Inspect its source for the exact value.');
    }
  }
  target.append(node(card.document));
  return true;
}
async function prepare(card, action, fields) {
  if (state.sending) throw new Error('Wait for the send result before preparing another action.');
  if (state.uncertain) throw new Error('Resolve or dismiss the uncertain draft before preparing another action.');
  if (authoring.pending || authoring.preparing || authoring.uncertain) throw new Error('Finish or resolve the source desk work before preparing another action.');
  const generation = ++state.preparationGeneration;
  const route = state.routeGeneration;
  const draft = await api('/api/prepare', { card, action, fields });
  if (generation !== state.preparationGeneration || route !== state.routeGeneration || state.card?.card !== card
      || state.sending || state.uncertain || authoring.pending || authoring.preparing || authoring.uncertain) return;
  if (draft.format === 'delvetalk-portal-preparation-v1') showPreparation(draft);
  else showDraft(draft);
}
function showPreparation(result) {
  state.draft = null;
  state.preparation = result;
  state.uncertain = false;
  clearRepositoryRecord();
  preparationAnswers.replaceChildren();
  const question = result.outcome.kind === 'question';
  $('draft-title').textContent = question ? 'A question from this object' : 'Preparation declined';
  $('draft-summary').textContent = text(result.outcome.message);
  $('draft-fields').replaceChildren();
  $('draft-target').textContent = `${text(result.object)} · read at version ${text(result.version)}`;
  for (const id of ['draft-absence', 'draft-command-row', 'preview-copy', 'send-draft', 'repository-export']) $(id).hidden = true;
  $('send-draft').disabled = true;
  $('draft-wire').textContent = '';
  document.querySelector('.draft-exact').hidden = true;
  $('draft-state').textContent = '';
  $('draft-help').textContent = 'Nothing has been submitted. These answers belong to the captured reading.';
  const needs = Array.isArray(result.outcome.needs) ? [...new Set(result.outcome.needs.filter(name => typeof name === 'string'))] : [];
  if (question && needs.length) {
    const action = state.card?.actions?.find(item => item.id === result.action);
    const form = element('form', 'action');
    const controls = needs.map((name, index) => {
      const field = action?.fields?.find(item => item.name === name)
        || { name, label: name, type: 'string', minLength: 0, maxLength: 65536 };
      const control = fieldInput(field, 'answer', index, true);
      if (Object.hasOwn(result.fields || {}, name)) {
        const value = result.fields[name];
        control.input.value = field.type === 'enum' ? String(field.options.indexOf(value)) : text(value);
      }
      form.append(control.label);
      return control;
    });
    const submit = element('button', 'secondary', 'Continue');
    submit.type = 'submit';
    form.append(submit);
    form.addEventListener('submit', event => {
      event.preventDefault();
      busy(submit, 'Preparing…', async () => {
        const answers = Object.assign(Object.create(null), result.fields || {}, readFields(controls));
        if (!form.reportValidity()) return;
        await prepare(result.card, result.action, answers);
      });
    });
    preparationAnswers.append(form);
  }
  const url = new URL(location.href);
  url.searchParams.delete('draft');
  url.searchParams.set('preparation', result.preparation);
  writeLocation(url);
  $('draft-panel').hidden = false;
  $('draft-panel').focus({ preventScroll: true });
}
function showDraft(draft, restored = false) {
  state.draft = draft;
  state.preparation = null;
  preparationAnswers.replaceChildren();
  document.querySelector('.draft-exact').hidden = false;
  $('repository-export').hidden = state.world.mode === 'public-preview' || state.world.capabilities?.repository === false;
  clearRepositoryRecord();
  state.uncertain = restored && draft.outcome == null && state.world.mode !== 'public-preview';
  const preview = state.world.mode === 'public-preview';
  $('draft-title').textContent = preview ? 'Your action preview' : 'A proposed action';
  $('draft-summary').textContent = text(draft.summary);
  $('draft-fields').replaceChildren();
  for (const [name, value] of Object.entries(draft.fields || {})) {
    $('draft-fields').append(element('dt', '', name), element('dd', '', text(value)));
  }
  $('preview-copy').hidden = !preview;
  $('draft-command-row').hidden = preview;
  $('send-draft').hidden = preview;
  $('draft-target').textContent = draft.reads?.length
    ? `Captured together: ${draft.reads.map(read => `${text(read.object)} · ${read.version == null ? "captured root" : `version ${text(read.version)}`}`).join('; ')}. All steps commit together.`
    : draft.object ? `${text(draft.object)}${draft.version == null ? '' : ` · read at version ${text(draft.version)}`}` : '';
  $('draft-absence').hidden = !draft.absence?.length;
  $('draft-absence').textContent = draft.absence?.length ? `Creates: ${draft.absence.join(', ')}. These object names must still be absent.` : '';
  $('draft-command').textContent = text(draft.token || draft.command || draft.draft);
  // Exact server JSON travels as a string: parsing numeric roots into JS Numbers
  // would lose precision even though their independently retained execution is exact.
  $('draft-wire').textContent = typeof draft.wireJson === 'string'
    ? draft.wireJson : JSON.stringify(draft.wire ?? draft, null, 2);
  document.querySelector('.draft-exact').open = false;
  const settled = draft.outcome === 'committed' || draft.outcome === 'refused';
  $('draft-state').textContent = settled ? `Retained outcome: ${draft.outcome}.` : '';
  const canSend = draft.canExecute === true && state.world.mode === 'local-interactive' && !settled;
  $('send-draft').disabled = !canSend;
  $('send-draft').textContent = settled ? 'Outcome retained' : restored ? 'Send / retry saved draft' : 'Send action';
  $('draft-help').textContent = state.world.mode === 'public-preview'
    ? 'This is an unsent preview, not a town reply. Copy a summary to keep your idea. The exact request is optional technical detail; sending requires an authenticated receiving route.'
    : settled
    ? 'This draft already has a retained receipt. Read the object again before preparing a new action.'
    : canSend
      ? restored
        ? 'Your saved draft is restored with the same intent. Sending it recovers its receipt or submits that exact action.'
        : 'This draft is tied to the object you just read. Send it when you’re ready.'
    : state.world.mode === 'read-only'
      ? 'This world is read-only. You can copy the proposal and inspect its exact details.'
      : 'This proposal cannot be sent here. You can copy it and inspect its exact details.';
  const url = new URL(location.href);
  url.searchParams.delete('preparation');
  url.searchParams.set('draft', draft.draft);
  writeLocation(url);
  $('draft-panel').hidden = false;
  $('draft-panel').focus({ preventScroll: true });
  $('draft-panel').scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'nearest' });
}
async function executeDraft() {
  const draft = state.draft;
  if (!draft || state.sending || !draft.canExecute || state.world.mode !== 'local-interactive') return;
  state.sending = true;
  $('send-draft').disabled = true;
  $('dismiss-draft').disabled = true;
  $('draft-state').textContent = 'Sending…';
  try {
    const result = await api('/api/execute', { draft: draft.draft });
    if (state.draft !== draft) return;
    if (result.kind === 'uncertain') {
      state.uncertain = true;
      $('draft-state').textContent = text(result.summary) || 'The reply is uncertain.';
      $('draft-help').textContent = 'Keep this draft. Retry the same action to recover its receipt; don’t prepare a replacement.';
      $('send-draft').textContent = 'Retry this draft';
      $('send-draft').disabled = false;
    } else if (result.kind === 'refused') {
      state.uncertain = false;
      draft.outcome = 'refused';
      $('draft-state').textContent = text(result.summary) || 'The action was refused.';
      $('draft-help').textContent = 'Read the object again before choosing a new action. A stale draft needs a fresh reading and a new intent.';
      notice(result.summary || 'The object did not accept this action.', true);
    } else if (result.kind === 'committed') {
      state.uncertain = false;
      draft.outcome = 'committed';
      $('draft-state').textContent = text(result.summary) || 'The action was committed.';
      $('draft-help').textContent = 'The world has kept a receipt. Read the object again to see what changed.';
      notice(result.summary || 'The action was committed. Read again to see the new state.');
      renderCreatedChildren(result.children || result.allocated || []);
      try { await loadWorld(); }
      catch { notice('The action committed, but the object shelf could not refresh. Its receipt is retained.'); }
    } else throw new Error('The portal returned an unknown action outcome.');
  } catch (error) {
    if (state.draft === draft) {
      state.uncertain = true;
      $('draft-state').textContent = error.message;
      $('draft-help').textContent = 'The outcome may be unknown. Keep this draft and retry it to recover the same receipt.';
      $('send-draft').textContent = 'Retry this draft';
      $('send-draft').disabled = false;
    }
  } finally {
    state.sending = false;
    $('dismiss-draft').disabled = false;
  }
}
async function loadDetail() {
  const card = state.card;
  if (!card || state.detail) return;
  try {
    const detail = await api(`/api/detail?card=${encodeURIComponent(card.card)}`);
    if (state.card !== card) return;
    state.detail = detail;
    const exact = detail.exact || {};
    const sections = ['source', 'state', 'law', 'root', 'history', 'runtime'].filter(key => Object.hasOwn(detail, key));
    sections.push('all');
    const exactRecord = '{\n' + Object.entries(detail).filter(([key]) => key !== 'exact')
      .map(([key, value]) => `  ${JSON.stringify(key)}: ${typeof exact[key] === 'string' ? exact[key] : JSON.stringify(value, null, 2)}`)
      .join(',\n') + '\n}';
    const show = key => {
      const value = key === 'all' ? detail : detail[key];
      $('detail-content').textContent = key === 'all' ? exactRecord
        : typeof exact[key] === 'string' ? exact[key]
          : JSON.stringify(value, null, 2);
      for (const button of $('detail-tabs').children) button.setAttribute('aria-pressed', String(button.dataset.key === key));
    };
    $('detail-tabs').replaceChildren();
    for (const key of sections) {
      const button = element('button', '', key === 'all' ? 'Exact record' : key[0].toUpperCase() + key.slice(1));
      button.type = 'button';
      button.dataset.key = key;
      button.addEventListener('click', () => show(key));
      $('detail-tabs').append(button);
    }
    show(sections[0]);
    $('copy-detail').disabled = false;
  } catch (error) { if (state.card === card) $('detail-content').textContent = error.message; }
}
$('inspect').addEventListener('toggle', () => { if ($('inspect').open) loadDetail(); });
$('refresh-world').addEventListener('click', () => busy($('refresh-world'), '…', async () => {
  await loadWorld();
  notice('The object shelf is up to date.');
}));
$('refresh-object').addEventListener('click', () => {
  if (state.sending) return notice('Wait for the send result before replacing this reading.');
  if (state.card) openObject(state.card.object, false, state.card.panel || 'main');
});
$('dismiss-draft').addEventListener('click', clearDraft);
$('copy-preview').addEventListener('click', () => {
  if (!state.draft) return;
  const lines = ['Unsent action preview', state.draft.summary, `Object: ${state.draft.object}`,
    ...Object.entries(state.draft.fields || {}).map(([key, value]) => `${key}: ${text(value)}`),
    'This summary is not an executable town reply.'];
  copy(lines.join('\n'), $('copy-preview'));
});
$('copy-draft').addEventListener('click', () => copy($('draft-command').textContent, $('copy-draft')));
$('copy-wire').addEventListener('click', () => copy($('draft-wire').textContent, $('copy-wire')));
$('download-wire').addEventListener('click', () => {
  const url = URL.createObjectURL(new Blob([$('draft-wire').textContent], { type: 'application/json;charset=utf-8' }));
  const link = element('a');
  link.href = url;
  link.download = 'delvetalk-proposal.json';
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
$('copy-repository').addEventListener('click', () => copy($('repository-json').textContent, $('copy-repository')));
$('prepare-repository').addEventListener('click', () => {
  const draft = state.draft;
  if (!draft) return;
  busy($('prepare-repository'), 'Preparing record…', async () => {
    const record = await api('/api/repository/prepare', { draft: draft.draft });
    if (state.draft !== draft) return;
    if (typeof record.recordJson !== 'string') throw new Error('The portal did not return an exact repository record.');
    $('repository-json').textContent = record.recordJson;
    $('repository-status').textContent = 'Record prepared. Nothing has been published, authenticated or sent.';
    $('repository-record').hidden = false;
  });
});
$('copy-detail').addEventListener('click', () => copy($('detail-content').textContent, $('copy-detail')));
$('copy-reference').addEventListener('click', () => {
  if (state.card?.objectRef) copy(JSON.stringify(state.card.objectRef), $('copy-reference'));
});
$('send-draft').addEventListener('click', executeDraft);
$('interpret-form').addEventListener('submit', event => {
  event.preventDefault();
  const card = state.card;
  if (!card) return;
  const button = event.submitter;
  busy(button, 'Thinking…', async () => {
    const proposal = await api('/api/interpret', { card: card.card, text: $('intent-text').value });
    if (state.card !== card) return;
    $('interpret-result').replaceChildren(element('p', '', proposal.message || proposal.summary || ''));
    if (proposal.status === 'proposed' && proposal.action) {
      await prepare(card.card, proposal.action, proposal.fields || {});
    } else if (proposal.status === 'partial' && proposal.action) {
      renderPartialInterpretation($('interpret-result'), proposal, () => prepare(card.card, proposal.action, proposal.fields || {}));
    }
  });
});
function renderViewChildren(card) {
  const target = $('view-children');
  target.replaceChildren();
  const children = card.children || [];
  target.hidden = children.length === 0;
  if (!children.length) return;
  target.append(element('h3', '', 'Look around'));
  target.append(element('p', 'help', 'These are places to read, not actions. Opening one reads its current state separately from this catalogue.'));
  const links = element('div', 'child-links');
  for (const child of children) {
    const button = element('button', 'secondary', child.label);
    button.type = 'button';
    button.addEventListener('click', () => openObject(child.object, true, child.panel, 'push',
      { card: card.card, key: child.key, label: child.label }));
    links.append(button);
  }
  target.append(links);
}
function renderCreatedChildren(children) {
  const target = $('object-children');
  target.replaceChildren();
  const valid = children.filter(child => child && typeof child.object === 'string');
  target.hidden = valid.length === 0;
  if (valid.length) target.append(element('p', 'help', 'Created in this committed action:'));
  for (const child of valid) {
    const button = element('button', 'secondary', child.title || child.object);
    button.type = 'button';
    button.addEventListener('click', () => openObject(child.object, true));
    target.append(button);
  }
}
function renderPartialInterpretation(target, proposal, continueWith) {
  const fields = element('dl', 'draft-fields');
  for (const [key, value] of Object.entries(proposal.fields || {})) fields.append(element('dt', '', key), element('dd', '', text(value)));
  target.append(fields);
  if (proposal.unresolved?.length) target.append(element('p', 'help', `Still open: ${proposal.unresolved.join(', ')}`));
  const button = element('button', 'secondary', 'Continue with these details');
  button.type = 'button';
  button.addEventListener('click', () => busy(button, 'Preparing…', continueWith));
  target.append(button);
}
function configureAuthoring(config) {
  const enabled = Boolean(config) && state.world.mode !== 'public-preview' && state.world.capabilities?.authoring !== false;
  $('source-desk').hidden = !enabled;
  if (!enabled) return;
  const current = $('source-syntax').value;
  $('source-syntax').replaceChildren();
  for (const syntax of config.syntaxes || []) {
    const option = element('option', '', syntax);
    option.value = syntax;
    $('source-syntax').append(option);
  }
  if ([...$('source-syntax').options].some(option => option.value === current)) $('source-syntax').value = current;
  if (!$('source-candidate').value && config.candidates?.length === 1) $('source-candidate').value = config.candidates[0];
  for (const [id, names] of [['candidate-objects', config.candidates || []], ['target-objects', (state.world.objects || []).map(object => object.id)]]) {
    $(id).replaceChildren();
    for (const name of names) {
      const option = element('option');
      option.value = name;
      $(id).append(option);
    }
  }
  if (!$('source-migration').value) $('source-migration').value = '{}';
}
function authoringUrl(id) {
  const url = new URL(location.href);
  if (id) url.searchParams.set('work', id);
  else url.searchParams.delete('work');
  writeLocation(url);
}
function clearAuthoring() {
  if (authoring.pending) return;
  authoring.draft = null;
  authoring.status = null;
  authoring.uncertain = false;
  $('authoring-work').hidden = true;
  authoringUrl(null);
}
async function retainSourceText(value, kind = 'source') {
  const limit = kind === 'scenarios' ? 1048576 : state.world.authoring?.maxSourceBytes || 524288;
  if (new TextEncoder().encode(value).length > limit) throw new Error(`The source limit is ${limit.toLocaleString()} UTF-8 bytes.`);
  return api('/api/authoring/source', { text: value, kind });
}
function exactSourceText(id) {
  const retained = authoring.rawFiles[id];
  return retained?.display === $(id).value ? retained.exact : $(id).value;
}
async function keepSource() {
  const sourceText = exactSourceText('source-text');
  const saved = await retainSourceText(sourceText);
  authoring.source = saved.source;
  authoring.sourceText = $('source-text').value;
  $('source-reference').value = saved.source;
  $('source-retained').textContent = `Kept · ${saved.bytes.toLocaleString()} bytes · ${saved.source.slice(0, 12)}`;
  return saved.source;
}
function updateAuthoringControls() {
  const draft = authoring.draft;
  if (!draft) return;
  const settled = draft.outcome === 'committed' || draft.outcome === 'refused' || Boolean(authoring.status?.job);
  $('send-authoring').disabled = authoring.pending || settled || !draft.canExecute || state.world.mode !== 'local-interactive';
  $('send-authoring').textContent = authoring.status?.job ? 'Job retained' : settled ? 'Outcome retained' : authoring.uncertain ? 'Send / retry saved proposal' : 'Send proposal';
  $('dismiss-authoring').disabled = authoring.pending;
  const phase = authoring.status?.phase;
  $('run-authoring').hidden = draft.operation !== 'compile' || !['queued', 'running'].includes(phase);
  $('run-authoring').disabled = authoring.pending || state.world.mode !== 'local-interactive';
  $('refresh-authoring').disabled = authoring.pending;
}
function showAuthoringDraft(draft, restored = false) {
  authoring.draft = draft;
  authoring.status = null;
  authoring.uncertain = restored && !draft.outcome;
  $('authoring-summary').textContent = text(draft.summary);
  $('authoring-title').textContent = `${draft.operation[0].toUpperCase() + draft.operation.slice(1)} proposal`;
  $('authoring-alias').textContent = `work ${draft.draft.slice(0, 12)}`;
  $('authoring-exact').textContent = draft.wireJson || draft.requestJson || JSON.stringify(draft, null, 2);
  $('authoring-status-exact').hidden = true;
  $('authoring-diagnostics').hidden = true;
  $('authoring-status').textContent = draft.outcome
    ? `Retained outcome: ${draft.outcome}.`
    : restored ? 'Saved proposal restored with its original intent. Check status or send the same proposal to recover its receipt.'
      : state.world.mode === 'read-only' ? 'Prepared for review. Sending and compilation require a configured local session.'
        : 'Prepared only. Review the exact proposal before sending.';
  $('source-candidate').value = draft.candidate || $('source-candidate').value;
  if (draft.target) $('source-target').value = draft.target;
  $('source-desk').open = true;
  $('authoring-work').hidden = false;
  authoringUrl(draft.draft);
  updateAuthoringControls();
}
async function prepareAuthoring(operation) {
  if (authoring.pending || authoring.preparing || authoring.uncertain) throw new Error('Resolve or dismiss the saved source desk proposal before preparing another.');
  authoring.preparing = true;
  try {
    const candidate = $('source-candidate').value.trim();
    if (!candidate) throw new Error('Choose a candidate object.');
    const payload = { operation, candidate };
    if (operation !== 'compile') {
      payload.target = $('source-target').value.trim();
      if (!payload.target) throw new Error('Choose a target object.');
    }
    if (operation === 'submit') {
      payload.syntax = $('source-syntax').value;
      if (!payload.syntax) throw new Error('Choose a syntax.');
      payload.source = authoring.sourceText === $('source-text').value && authoring.source ? authoring.source : await keepSource();
      if (!$('source-scenarios').value.trim()) throw new Error('Supply the scenario JSON for this candidate.');
    payload.scenarios = (await retainSourceText(exactSourceText('source-scenarios'), 'scenarios')).source;
      payload.migrationJson = $('source-migration').value;
    }
    const draft = await api('/api/authoring/prepare', payload);
    showAuthoringDraft(draft);
  } finally { authoring.preparing = false; }
}
async function checkAuthoringStatus() {
  const draft = authoring.draft;
  if (!draft) return;
  const status = await api(`/api/authoring/status?draft=${encodeURIComponent(draft.draft)}`);
  if (authoring.draft !== draft) return;
  authoring.status = status;
  if (status.job) authoring.uncertain = false;
  if (status.receipt?.kind === 'committed' || status.receipt?.kind === 'refused') {
    draft.outcome = status.receipt.kind;
    authoring.uncertain = false;
  }
  const phaseLabels = { prepared: 'Proposal prepared', queued: 'Compile job queued', running: 'Compile job in progress', finished: draft.operation === 'compile' ? 'Compile job finished' : 'Proposal processed' };
  $('authoring-status').textContent = `${phaseLabels[status.phase] || text(status.phase)}${draft.outcome ? ` · ${draft.outcome}` : ''}${status.job ? ` · job ${status.job.slice(0, 12)}` : ''}`;
  const notes = [...(status.diagnostics || []), ...(status.errors || [])];
  $('authoring-diagnostics').hidden = notes.length === 0;
  $('authoring-notes').textContent = notes.map(note => typeof note === 'string' ? note : JSON.stringify(note, null, 2)).join('\n\n');
  $('authoring-status-exact').textContent = status.exactJson || JSON.stringify(status, null, 2);
  $('authoring-status-exact').hidden = false;
  updateAuthoringControls();
}
async function authoringAction(operation) {
  const draft = authoring.draft;
  if (!draft || authoring.pending || authoring.preparing || state.world.mode !== 'local-interactive') return;
  authoring.pending = true;
  updateAuthoringControls();
  $('authoring-status').textContent = operation === 'run' ? 'Running the saved compile job…' : 'Sending the saved proposal…';
  try {
    const reply = await api(`/api/authoring/${operation}`, { draft: draft.draft });
    if (authoring.draft !== draft) return;
    if (reply.kind === 'uncertain') authoring.uncertain = true;
    await checkAuthoringStatus();
    if (reply.children) renderCreatedChildren(reply.children);
    try { await loadWorld(); } catch { /* The retained work remains recoverable. */ }
  } catch (error) {
    if (authoring.draft === draft) {
      authoring.uncertain = true;
      $('authoring-status').textContent = `${error.message} Keep this saved proposal; check status or retry it to recover the same intent.`;
    }
  } finally { authoring.pending = false; updateAuthoringControls(); }
}
$('source-form').addEventListener('submit', event => { event.preventDefault(); busy($('prepare-source'), 'Preparing…', () => prepareAuthoring('submit')); });
$('prepare-compile').addEventListener('click', () => busy($('prepare-compile'), 'Preparing…', () => prepareAuthoring('compile')));
$('prepare-adopt').addEventListener('click', () => busy($('prepare-adopt'), 'Preparing…', () => prepareAuthoring('adopt')));
$('retain-source').addEventListener('click', () => busy($('retain-source'), 'Keeping…', keepSource));
$('load-source').addEventListener('click', () => busy($('load-source'), 'Opening…', async () => {
  const source = $('source-reference').value.trim();
  const saved = await api(`/api/authoring/source?source=${encodeURIComponent(source)}`);
  $('source-text').value = saved.text;
  authoring.rawFiles['source-text'] = { display: $('source-text').value, exact: saved.text };
  authoring.source = saved.source || source;
  authoring.sourceText = $('source-text').value;
  $('source-retained').textContent = `Opened retained source · ${source.slice(0, 12)}`;
}));
for (const [fileId, textId] of [['source-file', 'source-text'], ['scenario-file', 'source-scenarios']]) {
  $(fileId).addEventListener('change', async () => {
    const file = $(fileId).files[0];
    if (!file) return;
    try {
      const limit = fileId === 'scenario-file' ? 1048576 : state.world.authoring?.maxSourceBytes || 524288;
      if (file.size > limit) throw new Error('This file exceeds the source size limit.');
      const exact = new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(await file.arrayBuffer());
      $(textId).value = exact;
      authoring.rawFiles[textId] = { exact, display: $(textId).value };
      if (fileId === 'source-file') $('source-retained').textContent = 'File opened locally. Keep source to retain it.';
    } catch (error) { notice(error.message, true); }
  });
}
$('source-text').addEventListener('input', () => { $('source-retained').textContent = 'Edited · not yet retained'; });
$('dismiss-authoring').addEventListener('click', clearAuthoring);
$('copy-authoring').addEventListener('click', () => copy($('authoring-exact').textContent, $('copy-authoring')));
$('send-authoring').addEventListener('click', () => authoringAction('execute'));
$('run-authoring').addEventListener('click', () => authoringAction('run'));
$('refresh-authoring').addEventListener('click', () => busy($('refresh-authoring'), 'Checking…', checkAuthoringStatus));
async function openLocation() {
  try {
    if (state.sending || authoring.pending) {
      writeLocation(state.location);
      return notice('Wait for the send result before navigating.');
    }
    const routeGeneration = ++state.routeGeneration;
    const requestedParams = new URL(location.href).searchParams;
    const requested = requestedParams.get('object');
    const savedDraftId = requestedParams.get('draft');
    const preparationId = requestedParams.get('preparation');
    const preparationGeneration = state.preparationGeneration;
    const workId = requestedParams.get('work');
    if (authoring.uncertain && authoring.draft && workId !== authoring.draft.draft) {
      const url = new URL(location.href);
      url.searchParams.set('work', authoring.draft.draft);
      writeLocation(url);
    }
    const world = state.world;
    let savedDraft = state.uncertain ? state.draft : null;
    let draftError = null;
    let savedPreparation = null;
    let preparationError = null;
    if (savedDraftId && !state.uncertain) {
      try { savedDraft = await api(`/api/draft?draft=${encodeURIComponent(savedDraftId)}`); }
      catch (error) { draftError = error; }
    }
    if (preparationId && !savedDraftId && !state.uncertain) {
      try { savedPreparation = await api(`/api/preparation?preparation=${encodeURIComponent(preparationId)}`); }
      catch (error) { preparationError = error; }
    }
    if (routeGeneration !== state.routeGeneration) return;
    if (savedPreparation && (preparationGeneration !== state.preparationGeneration || state.sending || state.uncertain
        || authoring.pending || authoring.preparing || authoring.uncertain)) {
      if (state.uncertain && state.draft) {
        const kept = new URL(state.location);
        kept.searchParams.set('draft', state.draft.draft);
        kept.searchParams.delete('preparation');
        writeLocation(kept);
      } else if (state.sending || authoring.pending || authoring.preparing || authoring.uncertain) writeLocation(state.location);
      return;
    }
    const id = savedPreparation?.object || (world.objects || []).find(object => object.id === requested)?.id
      || savedDraft?.object || world.defaultObject || world.objects?.[0]?.id;
    const panel = requestedParams.get('panel') || (savedDraft?.object === id ? savedDraft.panel : null) || 'main';
    if (id && !await openObject(id, false, panel, 'replace', null, savedPreparation?.card)) return;
    if (savedDraft) showDraft(savedDraft, true);
    else if (draftError) notice(`The saved draft could not be opened: ${draftError.message}`, true);
    else if (savedPreparation && preparationGeneration === state.preparationGeneration && !state.sending && !state.uncertain
        && !authoring.pending && !authoring.preparing && !authoring.uncertain) showPreparation(savedPreparation);
    else if (preparationError) notice(`The saved preparation could not be opened: ${preparationError.message}`, true);
    if (workId && !authoring.uncertain && world.authoring && world.capabilities?.authoring !== false) {
      // openObject advances the route generation. Capture its winning route,
      // then recheck after loading: a newer route or local work may now own the UI.
      const winningRoute = state.routeGeneration;
      const previousWork = authoring.draft;
      let restoredWork;
      const mayRestore = () => winningRoute === state.routeGeneration && !state.sending
        && !authoring.pending && !authoring.preparing && !authoring.uncertain
        && authoring.draft === previousWork;
      try {
        restoredWork = await api(`/api/authoring/draft?draft=${encodeURIComponent(workId)}`);
        if (!mayRestore()) return;
        showAuthoringDraft(restoredWork, true);
        await checkAuthoringStatus();
      } catch (error) {
        if (mayRestore() || (winningRoute === state.routeGeneration
            && authoring.draft === restoredWork && !authoring.pending))
          notice(`The saved source desk proposal could not be opened: ${error.message}`, true);
      }
    }
  } catch (error) { notice(error.message, true); }
}
window.addEventListener('popstate', openLocation);
// Authenticated visitor traffic uses the same receiving routes as network agents.
// Credentials are memory-only and never enter navigation, recovery data or posts.
async function agentApi(path, body, authenticated = true) {
  if (!/^\/AGENTS\.md(?:\/(?:verify|me|world|turn|repl|receipt))?(?:\?|$)/.test(path))
    throw new Error('Unknown agent API route.');
  if (authenticated && !agentSession.token) throw new Error('Connect with your API token first.');
  const headers = { Accept: 'application/json' };
  if (authenticated) headers.Authorization = `Bearer ${agentSession.token}`;
  const options = { headers, credentials: 'omit', redirect: 'error', cache: 'no-store' };
  if (body !== undefined) {
    options.method = 'POST';
    headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(body);
  }
  const response = await fetch(path, options);
  const raw = await response.text();
  let data;
  try { data = JSON.parse(raw); }
  catch { throw new Error(`The agent route returned an unreadable reply (${response.status}).`); }
  if (!response.ok) throw new Error(text(data.message || data.error) || `Agent request failed (${response.status}).`);
  return { data, raw };
}
function agentMessage(message) { $('agent-message').textContent = message; }
function agentHas(capability) { return agentSession.me?.capabilities?.[capability] === true; }
function renderAgentIdentity() {
  const me = agentSession.me;
  $('agent-connect').hidden = Boolean(me);
  $('agent-connected').hidden = !me;
  updateAgentWorkspace();
  if (!me) return;
  $('agent-identity-label').textContent = me.handle || `Connected · ${me.did.slice(0, 12)}…${me.did.slice(-4)}`;
  $('agent-identity-label').title = me.did;
  const enabled = Object.entries(me.capabilities || {}).filter(([, value]) => value === true).map(([key]) => key);
  $('agent-capabilities').textContent = `Available here: ${enabled.length ? enabled.join(', ') : 'inspection only'}. Each write still faces the current world rules.`;
  $('agent-prepare').disabled = !agentHas('turn');
  $('agent-repl-form').hidden = !agentHas('repl');
}
function updateAgentWorkspace() {
  const signedIn = Boolean(agentSession.me);
  const focused = signedIn && agentSession.surface !== 'public';
  document.querySelector('.workbench').classList.toggle('agent-focused', focused);
  $('agent-sidebar').hidden = !focused;
  $('resume-studio').hidden = !signedIn || focused;
  $('objects').hidden = focused;
  $('refresh-world').hidden = focused;
  if (focused) {
    $('agent-session').hidden = false;
    $('agent-session').open = true;
    $('agent-sidebar-controls').append($('agent-realm-controls'), $('agent-objects'));
    const realm = $('agent-realm').value;
    const name = realm === 'shared' ? 'Shared world' : 'Private studio';
    $('world-title').textContent = name;
    $('mode').textContent = name;
    $('principal').textContent = 'Your identity';
    $('footer-mode').textContent = realm === 'shared' ? 'A shared place, governed by its objects.' : 'Your source, notes and conversations.';
    $('agent-machine-label').textContent = realm === 'private' ? 'Write Bend / inspect source' : 'Exact request';
    document.querySelector('.skip').setAttribute('href', '#agent-encounter');
    document.title = `${agentSession.card?.title || name} · DelveTalk`;
  } else {
    $('agent-session').hidden = signedIn || state.world?.agents?.available === false;
    $('world-title').textContent = state.world?.title || 'The workbench';
    $('mode').textContent = state.world?.mode === 'public-preview' ? 'Public preview' : state.world?.mode === 'local-interactive' ? 'Local world' : 'Read-only world';
    $('principal').textContent = state.world?.principal ? `As ${state.world.principal}` : '';
    document.title = `${state.card?.title || 'A small world'} · DelveTalk`;
    document.querySelector('.skip').setAttribute('href', '#object-card');
    $('footer-mode').textContent = state.world?.mode === 'public-preview' ? 'Temporary previews · copy what you want to keep.' : 'Every action begins as a draft.';
  }
}
async function connectAgent(token) {
  if (agentSession.sending) throw new Error('Wait for the current reply before changing identity.');
  if (typeof token !== 'string' || !token.trim() || /[\x00-\x20\x7f]/.test(token)) throw new Error('Enter a valid API token.');
  const generation = ++agentSession.generation;
  agentSession.token = token;
  agentSession.me = null;
  $('agent-token').value = '';
  if ($('agent-issued-token').value !== token) {
    $('agent-issued-token').value = '';
    $('agent-issued').hidden = true;
  }
  $('agent-encounter').hidden = true;
  $('agent-root').hidden = true;
  try {
    const { data: me } = await agentApi('/AGENTS.md/me');
    if (generation !== agentSession.generation) return;
    if (!me.did || !Array.isArray(me.realms)) throw new Error('The identity reply is missing its realm contract.');
    agentSession.me = me;
    agentSession.surface = 'studio';
    $('agent-realm').replaceChildren();
    for (const realm of me.realms.filter(realm => realm === 'private' || realm === 'shared')) {
      const option = element('option', '', realm === 'private' ? 'Private studio' : 'Shared world');
      option.value = realm;
      $('agent-realm').append(option);
    }
    $('agent-realm').value = me.defaultRealm === 'shared' ? 'shared' : 'private';
    renderAgentIdentity();
    $('agent-proposal').hidden = !agentSession.proposal || agentSession.proposal.did !== me.did;
    agentMessage('Connected as your verified identity.');
    await readAgentWorld();
    await restoreAgentConversation();
  } catch (error) {
    if (generation === agentSession.generation && !agentSession.me) {
      agentSession.token = '';
      renderAgentIdentity();
    }
    throw error;
  }
}
function disconnectAgent() {
  if (agentSession.sending) return agentMessage('Wait for the reply before disconnecting.');
  ++agentSession.generation;
  ++agentSession.readGeneration;
  agentSession.token = '';
  agentSession.me = null;
  $('agent-token').value = '';
  $('agent-issued-token').value = '';
  $('agent-issued').hidden = true;
  $('agent-membership').hidden = true;
  agentSession.proof = null;
  $('agent-root-json').textContent = '';
  $('agent-encounter').hidden = true;
  $('agent-encounter-title').textContent = '';
  $('agent-encounter-prose').textContent = '';
  $('agent-encounter-actions').replaceChildren();
  $('agent-request').value = '';
  $('agent-repl-source').value = '';
  $('agent-recovery').value = '';
  $('agent-objects').replaceChildren();
  agentSession.card = null;
  renderAgentIdentity();
  agentMessage('Disconnected. No API token is stored in this browser. Reconnect as the same identity to recover any proposal still open in this page.');
}
async function readAgentWorld(path = null) {
  const generation = agentSession.generation;
  const read = ++agentSession.readGeneration;
  const realm = $('agent-realm').value;
  if (!agentSession.me || !['private', 'shared'].includes(realm)) return;
  $('agent-repl-form').hidden = realm !== 'private' || !agentHas('repl');
  const keepSelection = agentSession.card?.realm === realm;
  if (!keepSelection) $('agent-encounter').hidden = true;
  const { data } = await agentApi(path || `/AGENTS.md/world?realm=${realm}`);
  if (generation !== agentSession.generation || read !== agentSession.readGeneration) return;
  $('agent-objects').replaceChildren();
  if (!keepSelection) $('agent-root').hidden = true;
  for (const object of data.objects || []) {
    if (typeof object.object !== 'string') continue;
    const button = element('button', 'secondary', object.name || object.object);
    button.title = object.object;
    button.dataset.object = object.object;
    button.setAttribute('aria-current', String(agentSession.card?.object === object.object && agentSession.card?.realm === realm));
    button.type = 'button';
    button.addEventListener('click', () => busy(button, 'Reading…', () => openAgentObject(object.object, realm)));
    $('agent-objects').append(button);
  }
  if (!$('agent-objects').childElementCount) $('agent-objects').append(element('p', 'help', 'No objects in this realm yet.'));
  if (data.links?.next) {
    const next = element('button', 'secondary', 'Next page');
    next.type = 'button';
    next.addEventListener('click', async () => {
      next.disabled = true;
      try { await readAgentWorld(data.links.next); }
      catch (error) { agentMessage(`${error.message} Refresh this realm to start a new listing.`); }
      finally { next.disabled = false; }
    });
    $('agent-objects').append(next);
  }
  agentMessage(realm === 'private' ? 'Your private studio. Keep source, make objects, and return to your work.' : 'A shared place. Open an object to see what it offers your identity.');
  const first = (data.objects || []).find(object => object.object === data.defaultObject) || data.objects?.[0];
  if (!keepSelection && first) await openAgentObject(first.object, realm);
  updateAgentWorkspace();
}
async function refreshAgentWorld() {
  const card = agentSession.card;
  const generation = agentSession.generation;
  await readAgentWorld();
  // Paging preserves the captured reading; an explicit refresh asks the source
  // for a new one. Do not displace a selection made while the shelf was loading.
  if (generation === agentSession.generation && card && agentSession.card === card && card.realm === $('agent-realm').value)
    await openAgentObject(card.object, card.realm);
}
async function openAgentObject(object, realm, captured = null) {
  const generation = agentSession.generation;
  const read = ++agentSession.readGeneration;
  const response = captured ? { data: captured } : await agentApi(`/AGENTS.md/world?realm=${realm}&object=${encodeURIComponent(object)}&view=encounter&panel=main`);
  if (generation !== agentSession.generation || read !== agentSession.readGeneration) return;
  const card = response.data;
  agentSession.card = { ...card, realm };
  updateAgentWorkspace();
  for (const button of $('agent-objects').children) if (button.dataset.object) button.setAttribute('aria-current', String(button.dataset.object === object));
  $('agent-encounter-title').textContent = card.title || object;
  $('agent-encounter-prose').textContent = text(card.prose);
  $('agent-encounter').hidden = false;
  $('agent-conversation').hidden = true;
  $('agent-encounter-actions').replaceChildren();
  for (const [index, action] of (card.actions || []).entries()) {
    const form = element('form', 'action');
    form.dataset.actionId = action.id;
    const caption = element('p', 'action-label', action.label || action.id);
    const fields = (action.fields || []).map((field, i) => fieldInput(field, `agent-${index}`, i, action.preparation === true));
    form.documentControls = fields;
    form.append(caption);
    if (action.description) form.append(element('p', 'help', action.description));
    const group = element('div', 'action-fields');
    fields.forEach(field => group.append(field.label));
    form.append(group);
    const button = element('button', 'secondary', 'Prepare');
    button.type = 'submit';
    button.disabled = !agentHas('turn') || action.available === false || action.inspectOnly === true;
    form.append(button);
    const offerDetails = element('details', 'document-offer-details');
    offerDetails.append(element('summary', '', 'Offer token'));
    const token = action.token || `do ${card.card} ${action.id}`;
    offerDetails.append(element('code', '', token));
    const copyToken = element('button', 'text-button', 'Copy token');
    copyToken.type = 'button';
    copyToken.addEventListener('click', () => copy(token, copyToken));
    offerDetails.append(copyToken);
    form.append(offerDetails);
    form.addEventListener('submit', event => {
      event.preventDefault();
      busy(button, 'Preparing…', async () => {
        const values = readFields(fields);
        if (form.reportValidity()) await prepareAgentAction({ ...card, realm }, action.id, values);
      });
    });
    $('agent-encounter-actions').append(form);
  }
  if (!card.actions?.length) $('agent-encounter-actions').append(element('p', 'help', card.unsupported || 'This object offers no actions in this reading.'));
  $('agent-encounter-prose').hidden = renderLivingDocument(card, $('agent-document'), $('agent-encounter-actions'), {
    reference: async node => {
      const { data: result } = await agentApi(`/AGENTS.md/world?realm=${realm}&childCard=${encodeURIComponent(card.card)}&childKey=${encodeURIComponent(node.childKey)}`);
      if (generation !== agentSession.generation || read !== agentSession.readGeneration) return;
      if (result.status !== 'opened') throw new Error(result.message || 'This reference is unavailable in the current world.');
      await openAgentObject(result.card.object, realm, result.card);
    },
  });
  $('agent-interpretation').replaceChildren();
  $('agent-intention').value = '';
  const pending = agentSession.conversations.get(`${agentSession.me.did}|${realm}|${object}`);
  if (pending) showAgentConversation(pending.card, pending.result);
  const root = await agentApi(`/AGENTS.md/world?realm=${realm}&detail=${encodeURIComponent(card.card)}`);
  if (generation !== agentSession.generation || read !== agentSession.readGeneration) return;
  const exactRoot = root.data.exact?.root || root.data.rootJson;
  if (typeof exactRoot === 'string') {
    $('agent-root-title').textContent = `Look inside ${card.title || object}`;
    const sections = root.data.exact || { root: exactRoot };
    $('agent-inspect-sections').replaceChildren();
    const choose = key => {
      $('agent-root-json').textContent = sections[key];
      for (const button of $('agent-inspect-sections').children) button.setAttribute('aria-pressed', String(button.dataset.key === key));
    };
    for (const key of ['source', 'state', 'law', 'history', 'root']) {
      if (typeof sections[key] !== 'string') continue;
      const button = element('button', '', key[0].toUpperCase() + key.slice(1));
      button.type = 'button';
      button.dataset.key = key;
      button.addEventListener('click', () => choose(key));
      $('agent-inspect-sections').append(button);
    }
    choose(typeof sections.source === 'string' ? 'source' : 'root');
    $('agent-root').hidden = false;
    $('agent-root').open = false;
  }
}
async function prepareAgentAction(card, action, fields) {
  if (!agentHas('turn') || agentSession.sending || agentSession.uncertain) throw new Error('Resolve the pending turn before preparing another.');
  const generation = agentSession.generation;
  const read = agentSession.readGeneration;
  const preparation = ++agentSession.prepareGeneration;
  const { data: result } = await agentApi('/AGENTS.md/turn', { realm: card.realm, operation: 'prepare', card: card.card, action, fields });
  if (generation !== agentSession.generation || preparation !== agentSession.prepareGeneration || agentSession.sending || agentSession.uncertain) return;
  if (result.format === 'delvetalk-portal-preparation-v1') {
    agentSession.conversations.set(`${agentSession.me.did}|${card.realm}|${card.object}`, { card, result });
    if (agentSession.card?.object === card.object && agentSession.card?.realm === card.realm) showAgentConversation(card, result);
  } else {
    if (read !== agentSession.readGeneration) return;
    showPreparedAgentDraft(card, result, fields);
  }
}
function showPreparedAgentDraft(card, draft, fields = {}) {
  if (agentSession.sending || agentSession.uncertain) throw new Error('Recover the pending turn before preparing another.');
  if (typeof draft?.draft !== 'string' || typeof draft.intent !== 'string') throw new Error('The prepared turn is missing its retained intent.');
  agentSession.conversations.delete(`${agentSession.me.did}|${card.realm}|${card.object}`);
  $('agent-conversation').hidden = true;
  showAgentProposal({ format: 'delvetalk-browser-turn-v1', did: agentSession.me.did, kind: 'draft', realm: card.realm,
    intent: draft.intent, draft: draft.draft, summary: draft.summary || 'An offered action', fields: draft.fields || fields, wireJson: draft.wireJson || '' });
}
function showAgentConversation(card, result) {
  agentSession.conversation = { card, result };
  $('agent-conversation').hidden = false;
  $('agent-conversation-title').textContent = result.outcome.kind === 'question' ? 'An ongoing conversation' : 'Preparation declined';
  $('agent-question').textContent = text(result.outcome.message);
  $('agent-answer').replaceChildren();
  $('copy-agent-conversation').hidden = typeof result.preparation !== 'string';
  if (result.outcome.kind !== 'question') return;
  const action = card.actions?.find(action => action.id === result.action);
  const fields = [...new Set(result.outcome.needs || [])].map((name, index) => {
    const field = action?.fields?.find(field => field.name === name) || { name, label: name, type: 'string', minLength: 0, maxLength: 65536 };
    return fieldInput(field, 'agent-answer', index, true);
  });
  const form = element('form', 'action');
  fields.forEach(field => form.append(field.label));
  const button = element('button', 'secondary', 'Continue conversation');
  button.type = 'submit';
  form.append(button);
  form.addEventListener('submit', event => {
    event.preventDefault();
    busy(button, 'Preparing…', async () => {
      const answers = Object.assign(Object.create(null), result.fields || {}, readFields(fields));
      if (form.reportValidity()) await prepareAgentAction(card, result.action, answers);
    });
  });
  $('agent-answer').append(form);
  fields[0]?.input.focus({ preventScroll: true });
}
async function restoreAgentConversation() {
  const params = new URL(location.href).searchParams;
  const preparation = params.get('conversation');
  const realm = params.get('agentRealm');
  if (!preparation || !['private', 'shared'].includes(realm) || !agentSession.me) return;
  const generation = agentSession.generation;
  const { data: result } = await agentApi(`/AGENTS.md/world?realm=${realm}&preparation=${encodeURIComponent(preparation)}`);
  if (generation !== agentSession.generation) return;
  const { data: card } = await agentApi(`/AGENTS.md/world?realm=${realm}&card=${encodeURIComponent(result.card)}`);
  if (generation !== agentSession.generation) return;
  $('agent-realm').value = realm;
  await readAgentWorld();
  if (generation !== agentSession.generation) return;
  const captured = { ...card, realm };
  agentSession.conversations.set(`${agentSession.me.did}|${realm}|${card.object}`, { card: captured, result });
  await openAgentObject(card.object, realm, captured);
}
async function enrollAgent() {
  if (agentSession.sending || agentSession.me) throw new Error('Disconnect before beginning another enrollment.');
  const identity = $('agent-handle').value.trim();
  if (!identity) throw new Error('Enter your Delve handle or DID.');
  const generation = ++agentSession.generation;
  const { data } = await agentApi('/AGENTS.md', identity.startsWith('did:') ? { did: identity } : { handle: identity }, false);
  if (generation !== agentSession.generation) return;
  if (data.status !== 'pending' || typeof data.token !== 'string' || typeof data.challenge?.text !== 'string') throw new Error('The enrollment route did not provide a public challenge.');
  agentSession.token = data.token;
  agentSession.challenge = data.challenge;
  $('agent-challenge-text').textContent = data.challenge.text;
  $('agent-challenge').hidden = false;
  $('agent-issued-token').value = data.token;
  $('agent-issued').hidden = false;
  agentMessage(`Post only the public challenge exactly as shown, without extra text. Then paste the post’s at:// URI below and verify it.${data.challenge.expiresAt ? ` Challenge expires: ${text(data.challenge.expiresAt)}.` : ''}`);
}
async function verifyAgent() {
  if (!agentSession.challenge || !agentSession.token) throw new Error('Create a challenge first.');
  const generation = agentSession.generation;
  const uri = $('agent-proof').value.trim();
  if (!uri.startsWith('at://')) throw new Error('Use the proof post’s at:// URI.');
  const { data } = await agentApi('/AGENTS.md/verify', { uri });
  if (generation !== agentSession.generation) return;
  if (data.status !== 'verified') throw new Error('The proof has not been verified.');
  await connectAgent(agentSession.token);
  agentSession.proof = uri;
  showAgentMembership(data.membership);
  $('agent-challenge').hidden = true;
  agentSession.challenge = null;
}
function showAgentMembership(membership) {
  $('agent-membership').hidden = !membership;
  if (!membership) return;
  const messages = {
    committed: 'Your identity is verified, and the shared welcome action committed. Each object still applies its current rules.',
    refused: 'Your identity is verified. The shared welcome action was refused; verification alone grants no shared-world authority.',
    pending: 'Your identity is verified. The shared welcome outcome is pending; check it again without making a new identity.',
    unconfigured: 'Your identity is verified. This host has no automatic shared welcome; access depends on each object’s current rules.',
  };
  $('agent-membership-message').textContent = messages[membership.status] || 'Identity verification and shared membership are separate.';
  $('agent-membership-retry').hidden = membership.status !== 'pending';
}
function newAgentProposal(kind, input) {
  if (agentSession.sending || agentSession.uncertain) throw new Error('Recover the pending receipt before replacing this proposal.');
  if (!agentHas(kind === 'turn' ? 'turn' : 'repl')) throw new Error('This capability is not available for your identity.');
  const realm = $('agent-realm').value;
  if (!['private', 'shared'].includes(realm)) throw new Error('Choose a realm.');
  if (kind === 'repl' && realm !== 'private') throw new Error('Programs run in your private studio. Switch there first.');
  if (kind === 'turn') {
    const request = JSON.parse(input);
    if (!request || typeof request !== 'object' || Array.isArray(request)) throw new Error('A native request must be a JSON object.');
    if (Object.hasOwn(request, 'principal') || Object.hasOwn(request, 'intent')) throw new Error('Leave principal and intent out of the request; identity and recovery supply them.');
  }
  const proposal = { format: 'delvetalk-browser-turn-v1', did: agentSession.me.did, kind, realm,
    intent: `browser:${crypto.randomUUID()}`, ...(kind === 'turn' ? { requestJson: input }
      : { repl: { modules: [{ name: 'Main', source: input }], entry: $('agent-repl-entry').value, arguments: [] } }) };
  showAgentProposal(proposal);
}
function showAgentProposal(proposal, restored = false) {
  if (proposal.did !== agentSession.me?.did) throw new Error('Reconnect as the identity named in this recovery record.');
  agentSession.proposal = proposal;
  agentSession.uncertain = restored;
  $('agent-proposal').hidden = false;
  $('agent-proposal-summary').textContent = `${proposal.summary || (proposal.kind === 'turn' ? 'Native request' : 'Bend program')} · ${proposal.realm === 'private' ? 'private studio' : 'shared world'} · ${restored ? 'restored with the same intent' : 'prepared, not sent'}.`;
  $('agent-proposal-json').textContent = JSON.stringify(proposal, null, 2);
  $('agent-proposal-fields').replaceChildren();
  for (const [key, value] of Object.entries(proposal.fields || {})) $('agent-proposal-fields').append(element('dt', '', key), element('dd', '', text(value)));
  $('agent-result').textContent = '';
  $('agent-result-detail').hidden = true;
  $('agent-send').disabled = !agentHas(proposal.kind === 'repl' ? 'repl' : 'turn');
  $('agent-send').textContent = restored ? 'Send / retry same turn' : 'Send turn';
  $('agent-receipt').disabled = false;
  $('agent-proposal').tabIndex = -1;
  $('agent-proposal').focus({ preventScroll: true });
}
function restoreAgentProposal(raw) {
  if (agentSession.sending || agentSession.uncertain) throw new Error('Recover the pending receipt before replacing this proposal.');
  const proposal = JSON.parse(raw);
  const allowed = ['format', 'did', 'kind', 'realm', 'intent', ...(proposal?.kind === 'draft' ? ['draft', 'summary', 'fields', 'wireJson'] : [proposal?.kind === 'turn' ? 'requestJson' : 'repl'])];
  if (!proposal || proposal.format !== 'delvetalk-browser-turn-v1' || !['turn', 'repl', 'draft'].includes(proposal.kind)
      || !['private', 'shared'].includes(proposal.realm) || typeof proposal.intent !== 'string' || !proposal.intent
      || Object.keys(proposal).some(key => !allowed.includes(key))) throw new Error('This is not a supported recovery record.');
  if (proposal.kind === 'turn' && typeof proposal.requestJson !== 'string') throw new Error('The recovery request is missing.');
  if (proposal.kind === 'draft' && (typeof proposal.draft !== 'string' || !proposal.draft)) throw new Error('The retained draft reference is missing.');
  if (proposal.kind === 'repl' && (proposal.realm !== 'private' || !proposal.repl || typeof proposal.repl.entry !== 'string'
      || !Array.isArray(proposal.repl.modules) || !Array.isArray(proposal.repl.arguments)
      || Object.keys(proposal.repl).some(key => !['modules', 'entry', 'arguments'].includes(key)))) throw new Error('Invalid private program recovery record.');
  if (proposal.kind === 'turn') {
    const request = JSON.parse(proposal.requestJson);
    if (!request || typeof request !== 'object' || Array.isArray(request) || Object.hasOwn(request, 'principal') || Object.hasOwn(request, 'intent')) throw new Error('The recovery request must omit principal and intent.');
  }
  showAgentProposal(proposal, true);
}
function showAgentReply(result, raw) {
  const kind = (result.reply || result.receipt)?.kind;
  const settled = kind === 'committed' || kind === 'refused';
  agentSession.uncertain = !settled;
  $('agent-result').textContent = settled ? `Retained outcome: ${kind}.`
    : 'No confirmed outcome yet. Check the receipt or retry this exact proposal with the same intent.';
  $('agent-result-json').textContent = typeof result.replyJson === 'string' ? result.replyJson : raw;
  if (typeof result.evaluationJson === 'string') $('agent-result-json').textContent = `Evaluation\n${result.evaluationJson}\n\nReceipt\n${result.receiptJson || 'Not yet retained'}`;
  const value = result.evaluation?.value;
  if (settled && value && ['string', 'boolean', 'number'].includes(typeof value.value))
    $('agent-result').textContent = `Result: ${text(value.value)} · receipt ${kind}.`;
  $('agent-result-detail').hidden = false;
  $('agent-send').disabled = settled;
  $('agent-send').textContent = settled ? 'Outcome retained' : 'Retry same turn';
}
async function sendAgentProposal(receiptOnly = false) {
  const proposal = agentSession.proposal;
  if (!proposal || agentSession.sending || proposal.did !== agentSession.me?.did) return;
  if (!receiptOnly && !agentHas(proposal.kind === 'repl' ? 'repl' : 'turn')) return agentMessage('This capability is not available for your identity.');
  const generation = agentSession.generation;
  agentSession.sending = true;
  for (const id of ['agent-send', 'agent-receipt', 'agent-dismiss', 'agent-disconnect']) $(id).disabled = true;
  try {
    const response = receiptOnly
      ? await agentApi(`/AGENTS.md/receipt?realm=${proposal.realm}&intent=${encodeURIComponent(proposal.intent)}`)
      : proposal.kind === 'draft'
        ? await agentApi('/AGENTS.md/turn', { realm: proposal.realm, operation: 'execute', draft: proposal.draft })
        : await agentApi(`/AGENTS.md/${proposal.kind}`, { realm: proposal.realm, intent: proposal.intent,
          ...(proposal.kind === 'turn' ? { requestJson: proposal.requestJson } : proposal.repl) });
    if (generation !== agentSession.generation || agentSession.proposal !== proposal) return;
    showAgentReply(response.data, response.raw);
  } catch (error) {
    if (generation === agentSession.generation && agentSession.proposal === proposal) {
      agentSession.uncertain = true;
      $('agent-result').textContent = `${error.message} Keep this proposal and check its receipt before starting another turn.`;
      $('agent-send').disabled = false;
      $('agent-send').textContent = 'Retry same turn';
    }
  } finally {
    agentSession.sending = false;
    for (const id of ['agent-receipt', 'agent-dismiss', 'agent-disconnect']) $(id).disabled = false;
  }
}
$('agent-token-form').addEventListener('submit', event => { event.preventDefault(); busy(event.submitter, 'Connecting…', () => connectAgent($('agent-token').value)); });
$('agent-enroll-form').addEventListener('submit', event => { event.preventDefault(); busy(event.submitter, 'Creating…', enrollAgent); });
$('agent-verify-form').addEventListener('submit', event => { event.preventDefault(); busy(event.submitter, 'Verifying…', verifyAgent); });
$('agent-membership-retry').addEventListener('click', () => busy($('agent-membership-retry'), 'Checking…', async () => {
  if (!agentSession.proof) throw new Error('Keep your original proof URI to check its welcome outcome.');
  const generation = agentSession.generation;
  const { data } = await agentApi('/AGENTS.md/verify', { uri: agentSession.proof });
  if (generation === agentSession.generation) showAgentMembership(data.membership);
}));
$('copy-agent-challenge').addEventListener('click', () => copy($('agent-challenge-text').textContent, $('copy-agent-challenge')));
$('copy-agent-token').addEventListener('click', () => copy($('agent-issued-token').value, $('copy-agent-token')));
$('copy-agent-conversation').addEventListener('click', () => {
  const conversation = agentSession.conversation;
  if (!conversation?.result.preparation) return;
  const url = new URL(location.href);
  url.search = '';
  url.hash = '';
  url.searchParams.set('conversation', conversation.result.preparation);
  url.searchParams.set('agentRealm', conversation.card.realm);
  copy(url.href, $('copy-agent-conversation'));
});
$('agent-disconnect').addEventListener('click', disconnectAgent);
$('browse-public').addEventListener('click', () => { agentSession.surface = 'public'; updateAgentWorkspace(); });
$('resume-studio').addEventListener('click', () => { agentSession.surface = 'studio'; updateAgentWorkspace(); });
$('agent-realm').addEventListener('change', () => readAgentWorld().catch(error => agentMessage(error.message)));
$('agent-refresh').addEventListener('click', () => busy($('agent-refresh'), 'Reading…', refreshAgentWorld));
$('copy-agent-root').addEventListener('click', () => copy($('agent-root-json').textContent, $('copy-agent-root')));
$('copy-agent-proposal').addEventListener('click', () => copy($('agent-proposal-json').textContent, $('copy-agent-proposal')));
$('agent-turn-form').addEventListener('submit', event => { event.preventDefault(); try { newAgentProposal('turn', $('agent-request').value); } catch (error) { agentMessage(error.message); } });
$('agent-contribute').addEventListener('submit', event => {
  event.preventDefault();
  const card = agentSession.card;
  if (!card) return;
  busy($('agent-interpret'), 'Considering…', async () => {
    if (agentSession.sending || agentSession.uncertain) throw new Error('Recover the pending turn before preparing another.');
    const generation = agentSession.generation, read = agentSession.readGeneration, preparation = ++agentSession.prepareGeneration;
    const original = $('agent-intention').value;
    const { data: proposal } = await agentApi('/AGENTS.md/turn', { realm: card.realm, operation: 'interpret', card: card.card, text: original });
    if (generation !== agentSession.generation || read !== agentSession.readGeneration || preparation !== agentSession.prepareGeneration) return;
    const target = $('agent-interpretation');
    target.replaceChildren(element('blockquote', 'document-quote', original), element('p', '', proposal.message || proposal.summary || proposal.outcome?.message || (proposal.status === 'ready' ? 'A possibility is ready for your review.' : proposal.status)));
    if (proposal.status === 'ready' && proposal.draft) showPreparedAgentDraft(card, proposal.draft);
    else if (proposal.status === 'proposed' && proposal.action) await prepareAgentAction(card, proposal.action, proposal.fields || {});
    else if (proposal.status === 'partial' && proposal.action) renderPartialInterpretation(target, proposal, () => prepareAgentAction(card, proposal.action, proposal.fields || {}));
  });
});
for (const [input, form] of [['agent-intention', 'agent-contribute'], ['agent-repl-source', 'agent-repl-form']]) {
  $(input).addEventListener('keydown', event => {
    if (event.key === 'Enter' && (event.metaKey || event.ctrlKey) && !event.isComposing) {
      event.preventDefault();
      $(form).requestSubmit();
    }
  });
}
$('agent-repl-form').addEventListener('submit', event => { event.preventDefault(); try { newAgentProposal('repl', $('agent-repl-source').value); } catch (error) { agentMessage(error.message); } });
$('agent-repl-example').addEventListener('click', () => {
  if ($('agent-repl-source').value.trim()) return agentMessage('Your source is already here. Clear the editor first to load the example.');
  $('agent-repl-source').value = 'edition ObjectiveBend 1\ndef main() -> Nat:\n  6n * 7n\n';
  $('agent-repl-entry').value = 'main';
});
$('agent-recover-form').addEventListener('submit', event => { event.preventDefault(); try { restoreAgentProposal($('agent-recovery').value); } catch (error) { agentMessage(error.message); } });
$('agent-send').addEventListener('click', () => sendAgentProposal());
$('agent-receipt').addEventListener('click', () => sendAgentProposal(true));
$('agent-dismiss').addEventListener('click', () => {
  if (agentSession.sending) return;
  if (agentSession.uncertain) return agentMessage('This proposal has an uncertain outcome. Keep its recovery record and check the receipt before replacing it.');
  agentSession.proposal = null;
  $('agent-proposal').hidden = true;
});
(async () => {
  try { await loadWorld(); await openLocation(); }
  catch (error) { notice(error.message, true); $('mode').textContent = 'World unavailable'; }
})();
