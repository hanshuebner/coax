const axios = require('axios')
const crypto = require('crypto')
const http = require('http')

const httpAgent = new http.Agent({ keepAlive: true })

const API_ENDPOINT = process.argv[2] || 'http://192.168.1.143/transact';

function get_random_words(length) {
    const bytes = crypto.randomBytes(length * 2)
    for (let i = 0; i < length * 2; i += 2) {
        bytes[i+1] = bytes[i+1] & 0x03
    }
    return bytes
}

async function send_request(data) {
    try {
        const response = await axios.post(
            API_ENDPOINT,
            data,
            {
                responseType: 'arraybuffer',
                httpAgent
            })
        const response_data = Buffer.from(await response.data)
        if (response.status === 200 && Buffer.compare(data, response_data) === 0) {
            return true
        } else {
            console.error('Error: Response data does not match.')
            console.log('sent:', data)
            console.log('received:', response_data)
            return false
        }
    } catch (error) {
        console.error('Error:', error.message)
        return false
    }
}

async function main() {
    const WORDS_LENGTH = 8

    while (true) {
        const data = get_random_words(WORDS_LENGTH)
        const isSuccess = await send_request(data)
        if (!isSuccess) {
            break
        }
    }
}

main()
