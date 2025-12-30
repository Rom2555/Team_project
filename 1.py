import requests


class VK:

   def __init__(self, access_token, user_id, version='5.199'):
       self.token = access_token
       self.id = user_id
       self.version = version
       self.params = {'access_token': self.token, 'v': self.version}


   def users_info(self):
       url = 'https://api.vk.com/method/users.get'
       params = {'user_ids': self.id}
       response = requests.get(url, params={**self.params, **params})
       return response.json()

access_token = 'vk1.a.RDvvcYoiOmKhc9SX0NHLBikwukv7xnd8AMcMLT1qwPqU34eqBOBm9c8gbKVyBsX1ePobIuIkbcAr1v-CeY0kwxP35r9t_eYVGUgSz514Uddk8fEJOSgb4n-FNAWOW452gGdVXOFRaat74NIsL_eWkYeCZ8GHgrPq8ziIdzYDbNJqXvlh9Qwaq6nJGo4vl04H'
user_id = '1074315681'
vk = VK(access_token, user_id)


print(vk.users_info())