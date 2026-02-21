export const metrics = [
  {
    label: 'All tickets',
    value: '2,438',
    delta: '+12% today',
  },
  {
    label: 'VIP priority',
    value: '146',
    delta: '78% within SLA',
  },
  {
    label: 'Auto-assigned',
    value: '91%',
    delta: 'Avg 6.4s per ticket',
  },
  {
    label: 'Negative tone',
    value: '9.2%',
    delta: '-1.3% vs yesterday',
  },
]

export const tickets = [
  {
    id: 'TK-29310',
    client: 'A. Tleuova',
    city: 'Astana',
    type: 'Fraud alert',
    priority: 9,
    tone: 'Negative',
    lang: 'KZ',
    manager: 'E. Karimova',
  },
  {
    id: 'TK-29311',
    client: 'M. Sato',
    city: 'Almaty',
    type: 'Account update',
    priority: 7,
    tone: 'Neutral',
    lang: 'ENG',
    manager: 'I. Ospan',
  },
  {
    id: 'TK-29312',
    client: 'D. Kulen',
    city: 'Shymkent',
    type: 'App outage',
    priority: 8,
    tone: 'Negative',
    lang: 'RU',
    manager: 'S. Kassenov',
  },
  {
    id: 'TK-29313',
    client: 'L. Yoon',
    city: 'Abroad',
    type: 'Consultation',
    priority: 4,
    tone: 'Positive',
    lang: 'ENG',
    manager: 'A. Mirza',
  },
]

export const topManagers = [
  {
    name: 'E. Karimova',
    title: 'Lead Specialist',
    skills: ['VIP', 'KZ', 'ENG'],
    load: 8,
  },
  {
    name: 'I. Ospan',
    title: 'Chief Specialist',
    skills: ['VIP', 'ENG'],
    load: 6,
  },
  {
    name: 'S. Kassenov',
    title: 'Specialist',
    skills: ['KZ', 'RU'],
    load: 5,
  },
]
