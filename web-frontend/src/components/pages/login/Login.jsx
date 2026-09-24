import { useState } from 'react'
import { useDispatch } from 'react-redux'
import { useNavigate } from 'react-router-dom'
import { Alert, Button, Form, Input } from 'antd'
import { AuthHttpError, login } from '@/api/auth.js'
import { setSession } from '@/store/authSlice.js'
import './Login.css'

function errorText(error) {
  if (error instanceof AuthHttpError) {
    if (error.status === 400 || error.status === 401) {
      return 'Неверный логин или пароль'
    }

    if (error.status === 403) {
      return 'Нет доступа'
    }

    if (error.status === 503) {
      return 'Служба каталогов недоступна'
    }
  }

  return 'Не удалось войти'
}

export default function Login() {
  const dispatch = useDispatch()
  const navigate = useNavigate()
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  const onFinish = async ({ login: loginValue, password }) => {
    setError(null)
    setLoading(true)

    try {
      const accessToken = await login(loginValue, password)
      dispatch(setSession(accessToken))
      navigate('/', { replace: true })
    } catch (err) {
      setError(errorText(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-page">
      <div className="login-content">
        <div className="login-brand">Москоллектор</div>

        <div className="login-card">
          <h1 className="login-title">Авторизация</h1>
          <p className="login-subtitle">
            Введите логин и пароль, чтобы войти в аккаунт
          </p>

          {error ? (
            <Alert
              type="error"
              showIcon
              message={error}
              className="login-alert"
            />
          ) : null}

          <Form layout="vertical" requiredMark onFinish={onFinish}>
            <Form.Item
              name="login"
              label="Логин"
              rules={[{ required: true, message: 'Введите логин' }]}
            >
              <Input size="large" autoComplete="username" placeholder="Логин" />
            </Form.Item>

            <Form.Item
              name="password"
              label="Пароль"
              rules={[{ required: true, message: 'Введите пароль' }]}
            >
              <Input.Password
                size="large"
                autoComplete="current-password"
                placeholder="Пароль"
              />
            </Form.Item>

            <Form.Item className="login-submit-item">
              <Button
                className="login-submit"
                type="primary"
                htmlType="submit"
                loading={loading}
                block
                size="large"
              >
                Войти
              </Button>
            </Form.Item>
          </Form>
        </div>
      </div>
    </div>
  )
}
