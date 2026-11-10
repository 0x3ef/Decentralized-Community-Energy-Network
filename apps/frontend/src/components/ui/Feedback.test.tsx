import {afterEach,it,expect} from 'vitest'
import {render,screen,cleanup} from '@testing-library/react'
import {Feedback,Metric} from './Feedback'
afterEach(cleanup)
it('announces loading without showing unconfirmed content',()=>{render(<Feedback loading><p>Confirmed</p></Feedback>);expect(screen.getByRole('status').textContent).toContain('Loading');expect(screen.queryByText('Confirmed')).toBeNull()})
it('shows permission errors accessibly',()=>{render(<Feedback error={{response:{status:403}}}>Hidden</Feedback>);expect(screen.getByRole('alert').textContent).toContain('permission')})
it('shows an explicit empty state instead of invented balances',()=>{render(<Feedback empty>123 SUN</Feedback>);expect(screen.getByText(/No records yet/)).toBeTruthy();expect(screen.queryByText('123 SUN')).toBeNull()})
it('renders a labelled energy measurement',()=>{render(<Metric label="Verified injection" value="5 kWh"/>);expect(screen.getByText('5 kWh')).toBeTruthy()})
